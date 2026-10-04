import asyncio
import time
import html
import re
from datetime import datetime
import uuid
import aiohttp
import urllib.parse
import difflib

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot import app
from config import LOG_CHANNEL_ID
from filters.fsub import enforce_fsub
from utils.helpers import get_imdb_suggestions, get_imdb_movie_details
from database.models import search_files, increase_search_count, save_search_cache, update_search_state

print("✅ search.py imported", flush=True)

# ------------------------------------------------------------------
# IMDb selection storage
# Telegram callback_data is limited to 64 bytes.  We therefore keep
# only a short opaque token in callback_data.  The user NEVER sees it.
# ------------------------------------------------------------------
IMDB_SELECTIONS = {}
IMDB_SELECTION_TTL = 600


def store_imdb_selection(user_id, title):
    token = uuid.uuid4().hex[:16]
    IMDB_SELECTIONS[token] = {
        "user_id": int(user_id),
        "title": str(title).strip(),
        "created": time.time(),
    }
    return token


def get_imdb_selection_value(token, user_id):
    item = IMDB_SELECTIONS.get(str(token))
    if not item:
        return None
    if item.get("user_id") != int(user_id):
        return None
    if time.time() - float(item.get("created", 0)) > IMDB_SELECTION_TTL:
        IMDB_SELECTIONS.pop(str(token), None)
        return None
    return item.get("title")


def get_imdb_selection(token, user_id):
    return get_imdb_selection_value(token, user_id)


def cleanup_imdb_selections():
    now = time.time()
    expired = [
        key for key, value in IMDB_SELECTIONS.items()
        if now - float(value.get("created", 0)) > IMDB_SELECTION_TTL
    ]
    for key in expired:
        IMDB_SELECTIONS.pop(key, None)


# ================= SETTINGS ================= #
MENU_EXPIRE_SECONDS = 300
PAGE_LIMIT = 7

FIXED_LANGUAGES = [
    "All", "English", "Hindi", "Tamil", "Telugu", "Malayalam", "Kannada"
]

TMDB_LANG_MAP = {
    "Telugu": "te", "Tamil": "ta", "Hindi": "hi",
    "Malayalam": "ml", "Kannada": "kn", "English": "en"
}


# ================= HELPERS ================= #
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


KNOWN_LANGS = {
    "telugu": "Telugu", "tamil": "Tamil", "hindi": "Hindi",
    "english": "English", "malayalam": "Malayalam", "kannada": "Kannada"
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


def get_file_display_name(file):
    from utils.rename import clean_file_name
    raw_name = file.get("file_name") or file.get("original_file_name") or file.get("movie_name") or ""
    cleaned = clean_file_name(raw_name)
    if cleaned and cleaned.lower() != "unknown":
        return cleaned
    fallback = clean_file_name(file.get("movie_name") or "")
    if fallback and fallback.lower() != "unknown":
        return fallback
    return "Movie"


def imdb_title_text(title):
    """Human-readable IMDb button text; never exposes callback tokens/IDs."""
    text = str(title or "").strip()
    text = re.sub(r"\s*\((\d{4})\)\s*$", r" - \1", text)
    text = re.sub(r"\s+", " ", text)
    return text[:60]


def imdb_title_for_database(title):
    """Return the IMDb title and a year-free fallback used for DB search."""
    title = str(title or "").strip()
    title = re.sub(r"\s+", " ", title)
    year_match = re.search(r"\s*\((\d{4})\)\s*$", title)
    year = year_match.group(1) if year_match else None
    base = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    return title, base, year


def normalize_title(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def is_spelling_mistake(query, suggestions):
    query_norm = normalize_title(query)
    if not query_norm or not suggestions:
        return False
    best = 0.0
    exact = False
    for title in suggestions:
        _, base, _ = imdb_title_for_database(title)
        candidate = normalize_title(base)
        if candidate == query_norm:
            exact = True
        best = max(best, difflib.SequenceMatcher(None, query_norm, candidate).ratio())
    return not exact and best >= 0.72


async def search_selected_imdb_title(selected_title):
    """Search with the exact IMDb title first, then safely fall back to base title."""
    full_title, base_title, year = imdb_title_for_database(selected_title)

    results = await search_files(full_title)

    if not results and base_title and base_title.lower() != full_title.lower():
        results = await search_files(base_title)

    # If IMDb supplied a year, prefer matching files from that year when such
    # information exists.  Do not discard all files if the database stores no year.
    if results and year:
        year_matches = []
        for file in results:
            name = str(file.get("movie_name") or file.get("file_name") or "")
            file_year = str(file.get("year") or "")
            if year in name or file_year == year:
                year_matches.append(file)
        if year_matches:
            results = year_matches

    return results, full_title, base_title, year


# ================= SEARCH LOG ================= #
async def log_search(client, user, search_text, result_count=0):
    try:
        if not LOG_CHANNEL_ID:
            return
        username = f"@{user.username}" if user.username else "N/A"
        first_name = user.first_name or "N/A"
        result_status = (
            f"✅ <b>RESULTS FOUND:</b> <code>{result_count}</code>"
            if result_count > 0 else "❌ <b>NO RESULTS FOUND</b>"
        )
        log_text = (
            "🔍 <b>SEARCH USED</b>\n\n"
            f"👤 <b>Name:</b> {first_name}\n"
            f"📱 <b>Username:</b> {username}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"🔎 <b>Search:</b> <code>{html.escape(str(search_text))}</code>\n\n"
            f"{result_status}"
        )
        await client.send_message(LOG_CHANNEL_ID, log_text)
    except Exception as e:
        print(f"❌ SEARCH LOG ERROR : {e}", flush=True)


async def auto_delete_message(message, delay_seconds=40):
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception:
        pass


async def auto_delete_menu(client, chat_id, message_id):
    try:
        await asyncio.sleep(MENU_EXPIRE_SECONDS)
        await client.delete_messages(chat_id=chat_id, message_ids=message_id)
    except Exception:
        pass


# ================= LANGUAGE BUTTONS ================= #
def language_buttons(search_id, timestamp, selected=None):
    buttons, row = [], []
    for lang in FIXED_LANGUAGES:
        text = f"✅ {lang}" if selected == lang else lang
        row.append(InlineKeyboardButton(
            text,
            callback_data=f"lang:{lang}:{search_id}:{timestamp}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


# ================= DIRECT FILE BUTTON ================= #
def build_file_button(file, user_id, timestamp):
    display_name = get_file_display_name(file)
    file_size = format_size(file.get("file_size_bytes", 0))
    file_id = str(file.get("_id"))
    return InlineKeyboardButton(
        text=f"{file_size} | {display_name}",
        callback_data=f"file:{user_id}:{file_id}:{timestamp}"
    )


# ================= PAGINATION ================= #
def pagination_buttons(search_id, page, total, timestamp):
    row = []
    total_pages = max(1, (total + PAGE_LIMIT - 1) // PAGE_LIMIT)
    if page > 1:
        row.append(InlineKeyboardButton(
            "⪻ Previous", callback_data=f"page:{search_id}:{page - 1}:{timestamp}"
        ))
    row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="none"))
    if page < total_pages:
        row.append(InlineKeyboardButton(
            "Next ⪼", callback_data=f"page:{search_id}:{page + 1}:{timestamp}"
        ))
    return [row]


# ================= IMDb SELECTION MENU ================= #
async def send_imdb_selection_menu(client, user, chat_id, original_query, suggestions, reply_to_message_id=None):
    cleanup_imdb_selections()

    buttons = []
    for title in suggestions[:8]:
        token = store_imdb_selection(user.id, title)
        buttons.append([
            InlineKeyboardButton(
                imdb_title_text(title),
                callback_data=f"spell:{user.id}:{token}"
            )
        ])

    buttons.append([InlineKeyboardButton("✘ CLOSE ✘", callback_data="close")])

    if is_spelling_mistake(original_query, suggestions):
        text = (
            f"🔎 <b>{html.escape(original_query)}</b>\n\n"
            "⚠️ <b>Spelling Mistake Bro ‼️</b>\n\n"
            "😊 <b>Choose the correct movie below 👇🏻</b>"
        )
    else:
        text = (
            f"🎬 <b>Multiple Files Found for:</b> <code>{html.escape(original_query)}</code>\n\n"
            "👇🏻 <b>Choose The Files Below</b> 👇🏻"
        )

    msg = await client.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=reply_to_message_id
    )
    if msg:
        asyncio.create_task(auto_delete_message(msg, delay_seconds=60))
    return msg


# ================= CORE SEARCH EXECUTION ================= #
async def execute_search(client, user, chat_id, movie_name, reply_to_message_id=None, allow_spelling_suggestions=True):
    start_time = time.time()
    loading_msg = None
    selected_title = movie_name.strip()

    try:
        # Reaction
        try:
            from config import BOT_TOKEN
            reaction_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
            payload = {
                "chat_id": chat_id,
                "message_id": reply_to_message_id,
                "reaction": [{"type": "emoji", "emoji": "🤝"}],
                "is_big": True,
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
                await session.post(reaction_url, json=payload)
        except Exception:
            pass

        # Do NOT show the internal token/ID anywhere.  This is only a generic loading message.
        try:
            loading_msg = await client.send_message(
                chat_id=chat_id,
                text="**🔎 Searching IMDb . . .**",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            pass

        await asyncio.sleep(1.5)

        user_id = user.id
        print(f"🔍 SEARCH : {selected_title}", flush=True)
        asyncio.create_task(increase_search_count(user_id))

        # ------------------------------------------------------
        # ALWAYS start normal user searches with IMDb choices.
        # The actual database search happens only after a choice.
        # ------------------------------------------------------
        if allow_spelling_suggestions:
            has_explicit_year = False
            if "-" in selected_title:
                possible_year = selected_title.rsplit("-", 1)[-1].strip()
                has_explicit_year = possible_year.isdigit() and len(possible_year) == 4

            imdb_query = selected_title
            if has_explicit_year:
                imdb_query = selected_title.rsplit("-", 1)[0].strip()

            suggestions = await get_imdb_suggestions(imdb_query, limit=8)
            if suggestions:
                await send_imdb_selection_menu(
                    client=client,
                    user=user,
                    chat_id=chat_id,
                    original_query=selected_title,
                    suggestions=suggestions,
                    reply_to_message_id=reply_to_message_id,
                )
                return

        # ------------------------------------------------------
        # Selected IMDb title reaches here. Search DB using the
        # actual title, not callback token/ID.
        # ------------------------------------------------------
        results, imdb_full_title, imdb_base_title, imdb_year = await search_selected_imdb_title(selected_title)

        asyncio.create_task(log_search(client, user, imdb_full_title, len(results) if results else 0))

        # ================= NO RESULTS ================= #
        if not results:
            google_query = urllib.parse.quote_plus(imdb_base_title or imdb_full_title or selected_title)
            google_search_url = f"https://www.google.com/search?q={google_query}"

            no_result_text = (
                f"❌ <b>No files found for:</b> <code>{html.escape(imdb_full_title)}</code>\n\n"
                "📖 <b>Check the search instructions and try again.</b>\n"
                "🔍 <b>You can also search this title on Google.</b>"
            )
            no_result_buttons = [
                [InlineKeyboardButton("‼️ INSTRUCTIONS ‼️", callback_data="search_instructions")],
                [InlineKeyboardButton("♻️ GOOGLE SEARCH ♻️", url=google_search_url)],
            ]
            msg = await client.send_message(
                chat_id=chat_id,
                text=no_result_text,
                reply_markup=InlineKeyboardMarkup(no_result_buttons),
                reply_to_message_id=reply_to_message_id,
            )
            if msg:
                asyncio.create_task(auto_delete_message(msg, delay_seconds=40))
            return

        # ================= SEARCH METRICS & DETAILS ================= #
        elapsed_sec = f"{time.time() - start_time:.2f}"
        total_files_count = len(results)

        user_name = user.first_name or "User"
        user_mention = f'<a href="tg://user?id={user.id}"><b>{html.escape(user_name)}</b></a>'

        detected_audios = set()
        for file in results:
            detected_audios.update(extract_file_languages(file))

        priority_order = ["Telugu", "Tamil", "Hindi", "English", "Malayalam", "Kannada"]
        sorted_audios = [l for l in priority_order if l in detected_audios]
        for lang in detected_audios:
            if lang not in sorted_audios:
                sorted_audios.append(lang)
        audio_str = ", ".join(sorted_audios) if sorted_audios else "Multi"

        target_lang = "te"
        for lang in sorted_audios:
            if lang in TMDB_LANG_MAP:
                target_lang = TMDB_LANG_MAP[lang]
                break

        details_query = imdb_base_title or imdb_full_title
        movie_details = await get_imdb_movie_details(details_query, preferred_lang=target_lang)
        landscape_banner_url = movie_details.get("image") if movie_details else None

        caption_lines = []
        if movie_details and movie_details.get("title"):
            m_title = movie_details["title"]
            if imdb_year:
                m_title += f" - {imdb_year}"
            elif movie_details.get("year"):
                m_title += f" - {movie_details['year']}"
            caption_lines.append(f"🎬 <b>{html.escape(m_title)}</b>\n")
        else:
            caption_lines.append(f"🎬 <b>{html.escape(imdb_full_title.title())}</b>\n")

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
            "🥦 <b><i>Requested Files</i></b> 👇",
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

        asyncio.create_task(save_search_cache(search_id, cache_files, imdb_full_title))
        asyncio.create_task(update_search_state(search_id, cache_files[:PAGE_LIMIT], "All", 1))

        buttons = [[build_file_button(file, user_id, menu_timestamp)] for file in cache_files[:PAGE_LIMIT]]
        buttons.extend(language_buttons(search_id, menu_timestamp, selected="All"))
        buttons.append([InlineKeyboardButton(
            "📤 Send All",
            callback_data=f"all:{user_id}:{search_id}:{menu_timestamp}"
        )])
        buttons.extend(pagination_buttons(search_id, 1, len(cache_files), menu_timestamp))
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
                    reply_to_message_id=reply_to_message_id,
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
                                    reply_to_message_id=reply_to_message_id,
                                )
                                sent_success = True
                except Exception as b_err:
                    print(f"⚠️ Stream fallback error: {b_err}", flush=True)

        if not sent_success:
            sent_message = await client.send_message(
                chat_id=chat_id,
                text=final_caption,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
            )

        if sent_message:
            asyncio.create_task(auto_delete_menu(client, chat_id, sent_message.id))

        print("✅ SEARCH RESULT SENT SUCCESSFULLY", flush=True)

    except Exception as e:
        print(f"❌ SEARCH ERROR : {e}", flush=True)
        try:
            await client.send_message(chat_id, "⚠ Something went wrong.", reply_to_message_id=reply_to_message_id)
        except Exception:
            pass
    finally:
        if loading_msg:
            try:
                await loading_msg.delete()
            except Exception:
                pass


# ================= PRIVATE TEXT & SEARCH HANDLER ================= #
@app.on_message(
    filters.private
    & filters.text
    & ~filters.command([
        "start", "stats", "broadcast", "reindex", "reload", "ping",
        "usage", "owner", "delete", "generate_link", "imdb"
    ])
)
async def search_movie_handler(client, message: Message):
    try:
        if not message.from_user or message.via_bot:
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

        if not await enforce_fsub(client, message, payload=movie_name):
            return

        await execute_search(
            client=client,
            user=message.from_user,
            chat_id=message.chat.id,
            movie_name=movie_name,
            reply_to_message_id=message.id,
            allow_spelling_suggestions=True,
        )

    except Exception as e:
        print(f"❌ SEARCH HANDLER ERROR : {e}", flush=True)
        try:
            await message.reply_text("⚠️ Something went wrong.", quote=True)
        except Exception:
            pass
