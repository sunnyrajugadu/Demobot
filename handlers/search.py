import asyncio
import time
import html
import re
from datetime import datetime
import uuid
import aiohttp
import urllib.parse

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from bot import app
from config import LOG_CHANNEL_ID
from filters.fsub import enforce_fsub
from utils.helpers import get_imdb_suggestions, get_imdb_movie_details
from database.models import (
    search_files,
    increase_search_count,
    save_search_cache,
    update_search_state
)


print("✅ search.py imported", flush=True)


# ================= SETTINGS ================= #

MENU_EXPIRE_SECONDS = 300

PAGE_LIMIT = 7

FIXED_LANGUAGES = [
    "All",
    "English",
    "Hindi",
    "Tamil",
    "Telugu",
    "Malayalam",
    "Kannada"
]

TMDB_LANG_MAP = {
    "Telugu": "te",
    "Tamil": "ta",
    "Hindi": "hi",
    "Malayalam": "ml",
    "Kannada": "kn",
    "English": "en"
}


# ================= SIZE FORMAT ================= #

def format_size(size):
    try:
        size = int(size or 0)
    except Exception:
        size = 0

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.2f} MB"

    if size >= 1024:
        return f"{size / 1024:.2f} KB"

    return f"{size:.0f} B"


# ================= EXTRACT AUDIO LANGUAGES ================= #

KNOWN_LANGS = {
    "telugu": "Telugu",
    "tamil": "Tamil",
    "hindi": "Hindi",
    "english": "English",
    "malayalam": "Malayalam",
    "kannada": "Kannada"
}

def extract_file_languages(file):
    found = set()

    for key in ("audio", "languages", "language"):
        val = file.get(key)
        if isinstance(val, list):
            for v in val:
                v_str = str(v).strip().lower()
                if v_str in KNOWN_LANGS:
                    found.add(KNOWN_LANGS[v_str])
        elif isinstance(val, str) and val:
            for word, label in KNOWN_LANGS.items():
                if re.search(rf"\b{word}\b", val, re.IGNORECASE):
                    found.add(label)

    text_to_scan = f"{file.get('file_name', '')} {file.get('original_file_name', '')} {file.get('movie_name', '')}"
    for word, label in KNOWN_LANGS.items():
        if re.search(rf"\b{word}\b", text_to_scan, re.IGNORECASE):
            found.add(label)

    return list(found)


# ================= FILE DISPLAY NAME ================= #

def get_file_display_name(file):
    from utils.rename import clean_file_name

    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or ""
    )

    cleaned = clean_file_name(raw_name)

    if cleaned and cleaned.lower() != "unknown":
        return cleaned

    fallback = clean_file_name(file.get("movie_name") or "")

    if fallback and fallback.lower() != "unknown":
        return fallback

    return "Movie"


# ================= SMART MOVIE NAME CLEANER ================= #

def clean_movie_base_title(raw_name: str, query: str = "") -> str:
    from utils.rename import clean_file_name

    title = clean_file_name(raw_name)

    # 1. Strip URLs & domains
    title = re.sub(r"https?://\S+|www\.\S+|\b[a-zA-Z0-9_\-\.]+\.(com|org|net|in|top|click|link|xyz|site|fun|lol)\b", "", title, flags=re.IGNORECASE)

    # 2. Strip telegram channel handles & prefixes
    if query:
        q_clean = query.strip()
        match = re.search(re.escape(q_clean), title, flags=re.IGNORECASE)
        if match and match.start() > 0:
            title = title[match.start():]

    # Preserve release year
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
    preserved_year = year_match.group(1) if year_match else ""

    # 3. Strip all prints, resolutions, audios, codecs and tech flags
    tech_patterns = r"\b(20\d\d|19\d\d|720p|1080p|480p|2160p|4k|hq|prehd|hdrip|webrip|web-dl|web|dvdrip|cam|camrip|hdtc|hevc|x264|x265|aac|ac3|ddp|esub|sub|vers?|hdr|truehd|remux|avc)\b.*"
    title = re.sub(tech_patterns, "", title, flags=re.IGNORECASE)

    # 4. Strip languages from tail
    title = re.sub(r"\b(telugu|tamil|hindi|english|malayalam|kannada|multi|dual\s*audio)\b", "", title, flags=re.IGNORECASE)

    # 5. Clean trailing isolated letters/tags
    title = re.sub(r"\b(h|x|x2|aa|he|v1|v2|org|hq)\b", "", title, flags=re.IGNORECASE)

    # 6. Normalize punctuation and spaces
    title = re.sub(r"[_.\-+:]+", " ", title)
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    if preserved_year and preserved_year not in title and len(title.split()) == 1:
        title = f"{title} {preserved_year}"

    return title


def extract_distinct_movies(files_list, search_query: str):
    query_norm = search_query.lower().strip()
    raw_titles = []

    for f in files_list:
        raw = f.get("movie_name") or f.get("file_name") or f.get("original_file_name") or ""
        clean = clean_movie_base_title(raw, query=search_query)
        if clean and len(clean) >= 3 and query_norm in clean.lower():
            raw_titles.append(clean)

    distinct = []
    for cand in sorted(raw_titles, key=len):
        cand_lower = cand.lower().strip()
        matched = False
        for idx, exist in enumerate(distinct):
            exist_lower = exist.lower().strip()
            if cand_lower.startswith(exist_lower) or exist_lower.startswith(cand_lower):
                matched = True
                break
        if not matched:
            distinct.append(cand)

    collapsed = []
    for t in distinct:
        t_clean = t.title()
        if not any(t_clean.lower().startswith(c.lower()) and len(t_clean) > len(c) for c in collapsed):
            collapsed.append(t_clean)

    return collapsed if collapsed else [search_query.title()]


# ================= SEARCH LOG ================= #

async def log_search(
    client,
    user,
    search_text,
    result_count=0
):
    try:
        if not LOG_CHANNEL_ID:
            return

        username = (
            f"@{user.username}"
            if user.username
            else "N/A"
        )

        first_name = user.first_name or "N/A"

        if result_count > 0:
            result_status = (
                f"✅ <b>RESULTS FOUND:</b> "
                f"<code>{result_count}</code>"
            )
        else:
            result_status = "❌ <b>NO RESULTS FOUND</b>"

        log_text = (
            "🔍 <b>SEARCH USED</b>\n\n"
            f"👤 <b>Name:</b> {first_name}\n"
            f"📱 <b>Username:</b> {username}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"🔎 <b>Search:</b> <code>{search_text}</code>\n\n"
            f"{result_status}"
        )

        await client.send_message(
            LOG_CHANNEL_ID,
            log_text
        )

    except Exception as e:
        print(f"❌ SEARCH LOG ERROR : {e}", flush=True)


# ================= AUTO DELETE HELPER ================= #

async def auto_delete_message(message, delay_seconds: int = 40):
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception:
        pass


# ================= AUTO DELETE MENU AFTER EXPIRY ================= #

async def auto_delete_menu(client, chat_id, message_id):
    try:
        await asyncio.sleep(MENU_EXPIRE_SECONDS)
        await client.delete_messages(
            chat_id=chat_id,
            message_ids=message_id
        )
    except Exception:
        pass


# ================= LANGUAGE BUTTONS ================= #

def language_buttons(
    search_id,
    timestamp,
    selected=None
):
    buttons = []
    row = []

    for lang in FIXED_LANGUAGES:
        text = f"✅ {lang}" if selected == lang else lang

        row.append(
            InlineKeyboardButton(
                text,
                callback_data=(
                    f"lang:"
                    f"{lang}:"
                    f"{search_id}:"
                    f"{timestamp}"
                )
            )
        )

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return buttons


# ================= DIRECT FILE BUTTON ================= #

def build_file_button(
    file,
    user_id,
    timestamp
):
    display_name = get_file_display_name(file)

    file_size = format_size(
        file.get("file_size_bytes", 0)
    )

    file_id = str(file.get("_id"))

    return InlineKeyboardButton(
        text=f"{file_size} | {display_name}",
        callback_data=f"file:{user_id}:{file_id}:{timestamp}"
    )


# ================= PAGINATION ================= #

def pagination_buttons(
    search_id,
    page,
    total,
    timestamp
):
    row = []

    total_pages = (
        (total + PAGE_LIMIT - 1)
        // PAGE_LIMIT
    )

    if total_pages < 1:
        total_pages = 1

    if page > 1:
        row.append(
            InlineKeyboardButton(
                "⬅ Previous",
                callback_data=(
                    f"page:"
                    f"{search_id}:"
                    f"{page - 1}:"
                    f"{timestamp}"
                )
            )
        )

    row.append(
        InlineKeyboardButton(
            f"📄 {page}/{total_pages}",
            callback_data="none"
        )
    )

    if page < total_pages:
        row.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=(
                    f"page:"
                    f"{search_id}:"
                    f"{page + 1}:"
                    f"{timestamp}"
                )
            )
        )

    return [row]


# ================= CORE SEARCH EXECUTION ================= #

async def execute_search(
    client,
    user,
    chat_id,
    movie_name,
    reply_to_message_id=None,
    allow_spelling_suggestions=True
):
    start_time = time.time()
    try:
        user_id = user.id
        print(f"🔍 SEARCH : {movie_name}", flush=True)

        asyncio.create_task(increase_search_count(user_id))

        # 1. Search database
        results = await search_files(movie_name)

        if not results and "(" in movie_name:
            clean_name = movie_name.split("(")[0].strip()
            if clean_name:
                results = await search_files(clean_name)

        # 2. Check if DB has genuinely multiple franchise parts
        if results and allow_spelling_suggestions:
            distinct_db_movies = extract_distinct_movies(results, movie_name)

            if len(distinct_db_movies) > 1 and not (len(distinct_db_movies) == 1 and distinct_db_movies[0].lower() == movie_name.lower()):
                query_words = len(movie_name.strip().split())
                if query_words <= 2:
                    buttons = []
                    for title in distinct_db_movies[:8]:
                        buttons.append([
                            InlineKeyboardButton(
                                title,
                                callback_data=f"spell:{user_id}:{title[:45]}"
                            )
                        ])

                    buttons.append([InlineKeyboardButton("✘ CLOSE ✘", callback_data="close")])

                    prompt_msg = await client.send_message(
                        chat_id=chat_id,
                        text=(
                            f"🎬 **Multiple movies found for:** `{movie_name}`\n\n"
                            "👇 **Please select which movie you want:**"
                        ),
                        reply_markup=InlineKeyboardMarkup(buttons),
                        reply_to_message_id=reply_to_message_id
                    )

                    if prompt_msg:
                        asyncio.create_task(auto_delete_message(prompt_msg, delay_seconds=45))
                    return

        asyncio.create_task(
            log_search(
                client,
                user,
                movie_name,
                len(results) if results else 0
            )
        )

        # ================= NO RESULTS / SPELLING SUGGESTIONS ================= #
        if not results:
            if allow_spelling_suggestions:
                suggestions = await get_imdb_suggestions(movie_name, limit=8)
                if suggestions:
                    suggestion_buttons = []
                    for title in suggestions:
                        clean_disp = title.split("(")[0].strip() if "(" in title else title
                        cb_data = f"spell:{user_id}:{clean_disp[:45]}"
                        suggestion_buttons.append([InlineKeyboardButton(clean_disp, callback_data=cb_data)])

                    suggestion_buttons.append([InlineKeyboardButton("✘ CLOSE ✘", callback_data="close")])

                    reply_text = (
                        f"`{movie_name}`\n\n"
                        "**Spelling Mistake Bro ‼️**\n\n"
                        "**DON'T WORRY 😊 CHOOSE THE CORRECT ONE BELOW 👇**"
                    )

                    spell_msg = await client.send_message(
                        chat_id=chat_id,
                        text=reply_text,
                        reply_markup=InlineKeyboardMarkup(suggestion_buttons),
                        reply_to_message_id=reply_to_message_id
                    )

                    if spell_msg:
                        asyncio.create_task(auto_delete_message(spell_msg, delay_seconds=30))
                    return

            google_query = urllib.parse.quote_plus(movie_name)
            google_search_url = f"https://www.google.com/search?q={google_query}"

            no_result_text = f"""✨ **Oops! I couldn't find "{movie_name}" in my database** 📀

🔍 **Search on Google and check if your spelling is correct.**

📖 **Please read the instructions to get better results.**"""

            no_result_buttons = [
                [
                    InlineKeyboardButton("‼️ INSTRUCTIONS ‼️", callback_data="search_instructions")
                ],
                [
                    InlineKeyboardButton("♻️️ GOOGLE SEARCH ♻️", url=google_search_url)
                ]
            ]

            no_result_message = await client.send_message(
                chat_id=chat_id,
                text=no_result_text,
                reply_markup=InlineKeyboardMarkup(no_result_buttons),
                reply_to_message_id=reply_to_message_id
            )

            if no_result_message:
                asyncio.create_task(auto_delete_message(no_result_message, delay_seconds=40))

            return

        # ================= SEARCH METRICS & DETAILS ================= #
        elapsed_sec = f"{time.time() - start_time:.2f}"
        total_files_count = len(results)

        user_name = user.first_name or "User"
        user_mention = f'<a href="tg://user?id={user.id}"><b>{html.escape(user_name)}</b></a>'

        detected_audios = set()
        for f in results:
            langs = extract_file_languages(f)
            detected_audios.update(langs)

        priority_order = ["Telugu", "Tamil", "Hindi", "English", "Malayalam", "Kannada"]
        sorted_audios = [l for l in priority_order if l in detected_audios]
        for l in detected_audios:
            if l not in sorted_audios:
                sorted_audios.append(l)

        audio_str = ", ".join(sorted_audios) if sorted_audios else "Multi"

        target_lang = "te"
        for l in sorted_audios:
            if l in TMDB_LANG_MAP:
                target_lang = TMDB_LANG_MAP[l]
                break

        movie_details = await get_imdb_movie_details(movie_name, preferred_lang=target_lang)
        landscape_banner_url = movie_details.get("image") if movie_details else None

        caption_lines = []

        if movie_details and movie_details.get("title"):
            m_title = movie_details['title']
            if movie_details.get("year"):
                m_title += f" ({movie_details['year']})"
            caption_lines.append(f"🎬 <b>{html.escape(m_title)}</b>\n")
        else:
            caption_lines.append(f"🎬 <b>{html.escape(movie_name.title())}</b>\n")

        if movie_details:
            if movie_details.get("rating") and movie_details["rating"] != "N/A":
                caption_lines.append(f"⭐ <b>RATING :</b> <code>{movie_details['rating']} / 10</code>")

            if movie_details.get("genres") and movie_details["genres"] != "N/A":
                caption_lines.append(f"🎭 <b>GENRE :</b> <code>{movie_details['genres']}</code>")

            if movie_details.get("runtime") and movie_details["runtime"] != "N/A":
                caption_lines.append(f"⏳ <b>RUN TIME :</b> <code>{movie_details['runtime']}</code>")

        caption_lines.append(f"🔊 <b>AUDIO :</b> <code>{audio_str}</code>\n")

        caption_lines.extend([
            f"📁 <b>TOTAL FILES :</b> <code>{total_files_count}</code>",
            f"📝 <b>REQUESTED BY :</b> {user_mention}",
            f"⏰ <b>RESULT IN :</b> <code>{elapsed_sec} s</code>\n",
            "🥦 <b><i>Requested Files</i></b> 👇"
        ])

        final_caption = "\n".join(caption_lines)

        # ================= SEARCH ID & CACHING ================= #
        search_id = str(uuid.uuid4())
        menu_timestamp = int(datetime.now().timestamp())

        cache_files = []
        for file in results:
            if "_id" in file:
                file["_id"] = str(file["_id"])
            cache_files.append(file)

        asyncio.create_task(save_search_cache(search_id, cache_files, movie_name))
        asyncio.create_task(update_search_state(search_id, cache_files[:PAGE_LIMIT], "All", 1))

        # ================= BUILD BUTTONS ================= #
        buttons = []
        for file in cache_files[:PAGE_LIMIT]:
            buttons.append(
                [build_file_button(file, user_id, menu_timestamp)]
            )

        buttons.extend(
            language_buttons(
                search_id=search_id,
                timestamp=menu_timestamp,
                selected="All"
            )
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    "📤 Send All",
                    callback_data=(
                        f"all:"
                        f"{user_id}:"
                        f"{search_id}:"
                        f"{menu_timestamp}"
                    )
                )
            ]
        )

        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(cache_files),
                menu_timestamp
            )
        )

        reply_markup = InlineKeyboardMarkup(buttons)

        # ================= DISPATCH PHOTO BANNER ================= #
        sent_success = False
        sent_message = None
        
        if landscape_banner_url:
            try:
                sent_message = await client.send_photo(
                    chat_id=chat_id,
                    photo=landscape_banner_url,
                    caption=final_caption,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id
                )
                sent_success = True
            except Exception as pe:
                print(f"⚠️ Landscape direct URL failed ({pe}), attempting stream...", flush=True)
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(landscape_banner_url, timeout=aiohttp.ClientTimeout(total=4)) as img_resp:
                            if img_resp.status == 200:
                                img_bytes = await img_resp.read()
                                sent_message = await client.send_photo(
                                    chat_id=chat_id,
                                    photo=img_bytes,
                                    caption=final_caption,
                                    reply_markup=reply_markup,
                                    reply_to_message_id=reply_to_message_id
                                )
                                sent_success = True
                except Exception as b_err:
                    print(f"⚠️ Stream fallback error: {b_err}", flush=True)

        if not sent_success:
            sent_message = await client.send_message(
                chat_id=chat_id,
                text=final_caption,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id
            )

        # ====================================================
        # AUTO DELETE SEARCH MENU TASK
        # ====================================================
        if sent_message:
            asyncio.create_task(
                auto_delete_menu(
                    client=client,
                    chat_id=chat_id,
                    message_id=sent_message.id
                )
            )

        print("✅ SEARCH RESULT SENT SUCCESSFULLY", flush=True)

    except Exception as e:
        print(f"❌ SEARCH ERROR : {e}", flush=True)
        try:
            await client.send_message(chat_id, "⚠️️ Something went wrong.", reply_to_message_id=reply_to_message_id)
        except Exception:
            pass


# ================= PRIVATE TEXT & SEARCH HANDLER ================= #

@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(
        [
            "start",
            "stats",
            "broadcast",
            "reindex",
            "reload",
            "ping",
            "usage",
            "owner",
            "delete",
            "generate_link",
            "imdb"
        ]
    )
)
async def search_movie_handler(
    client,
    message: Message
):
    try:
        if not message.from_user:
            return

        if message.via_bot:
            return

        movie_name = (message.text or "").strip()

        if (
            "Size :-" in movie_name
            or "Size:" in movie_name
            or "@CinemaVetaBot" in movie_name
            or "@mrDuDeHoLic" in movie_name
            or movie_name.startswith("📁")
            or "Results -" in movie_name
        ):
            return

        if movie_name.startswith("@"):
            parts = movie_name.split()
            movie_name = " ".join(parts[1:])

        if movie_name.lower().startswith("/search"):
            movie_name = movie_name[7:].strip()

        if not movie_name:
            return

        # Force Subscribe Verification
        if not await enforce_fsub(client, message, payload=movie_name):
            return

        # Execute search
        await execute_search(
            client=client,
            user=message.from_user,
            chat_id=message.chat.id,
            movie_name=movie_name,
            reply_to_message_id=message.id,
            allow_spelling_suggestions=True
        )

    except Exception as e:
        print(f"❌ SEARCH HANDLER ERROR : {e}", flush=True)
        try:
            await message.reply_text("⚠️ Something went wrong.", quote=True)
        except Exception:
            pass
