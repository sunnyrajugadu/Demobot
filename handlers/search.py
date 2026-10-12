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
from database.models import (
    search_files,
    increase_search_count,
    save_search_cache,
    update_search_state
)

print("✅ search.py imported", flush=True)


# ================= SETTINGS =================

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


# ================= SIZE FORMAT =================

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


# ================= EXTRACT AUDIO LANGUAGES =================

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
                if re.search(
                    rf"\b{re.escape(word)}\b",
                    val,
                    re.IGNORECASE
                ):
                    found.add(label)

    text_to_scan = (
        f"{file.get('file_name', '')} "
        f"{file.get('original_file_name', '')} "
        f"{file.get('movie_name', '')}"
    )

    for word, label in KNOWN_LANGS.items():
        if re.search(
            rf"\b{re.escape(word)}\b",
            text_to_scan,
            re.IGNORECASE
        ):
            found.add(label)

    return list(found)


# ================= FILE DISPLAY NAME =================

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

    fallback = clean_file_name(
        file.get("movie_name") or ""
    )

    if fallback and fallback.lower() != "unknown":
        return fallback

    return "Movie"


# ================= SEARCH LOG =================

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
            f"🔎 <b>Search:</b> <code>{html.escape(search_text)}</code>\n\n"
            f"{result_status}"
        )

        await client.send_message(
            LOG_CHANNEL_ID,
            log_text
        )

    except Exception as e:
        print(
            f"❌ SEARCH LOG ERROR : {e}",
            flush=True
        )


# ================= AUTO DELETE HELPER =================

async def auto_delete_message(
    message,
    delay_seconds: int = 40
):
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception:
        pass


# ================= AUTO DELETE MENU =================

async def auto_delete_menu(
    client,
    chat_id,
    message_id
):
    try:
        await asyncio.sleep(
            MENU_EXPIRE_SECONDS
        )

        await client.delete_messages(
            chat_id=chat_id,
            message_ids=message_id
        )

    except Exception:
        pass


# ================= LANGUAGE BUTTONS =================

def language_buttons(
    search_id,
    timestamp,
    selected=None
):
    buttons = []
    row = []

    for lang in FIXED_LANGUAGES:

        text = (
            f"✅ {lang}"
            if selected == lang
            else lang
        )

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


# ================= DIRECT FILE BUTTON =================

def build_file_button(
    file,
    user_id,
    timestamp
):
    display_name = get_file_display_name(file)

    file_size = format_size(
        file.get("file_size_bytes", 0)
    )

    file_id = str(
        file.get("_id")
    )

    return InlineKeyboardButton(
        text=f"{file_size} | {display_name}",
        callback_data=(
            f"file:"
            f"{user_id}:"
            f"{file_id}:"
            f"{timestamp}"
        )
    )


# ================= PAGINATION =================

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
                "⪻ Previous",
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
                "Next ⪼",
                callback_data=(
                    f"page:"
                    f"{search_id}:"
                    f"{page + 1}:"
                    f"{timestamp}"
                )
            )
        )

    return [row]


# ============================================================
# CORE SEARCH EXECUTION
# ============================================================

async def execute_search(
    client,
    user,
    chat_id,
    movie_name,
    reply_to_message_id=None
):
    start_time = time.time()
    loading_msg = None

    try:

        # ====================================================
        # 1. REACTION + LOADING
        # ====================================================

        try:
            from config import BOT_TOKEN

            reaction_url = (
                "https://api.telegram.org/"
                f"bot{BOT_TOKEN}/setMessageReaction"
            )

            reaction_payload = {
                "chat_id": chat_id,
                "message_id": reply_to_message_id,
                "reaction": [
                    {
                        "type": "emoji",
                        "emoji": "🤝"
                    }
                ],
                "is_big": True
            }

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=2.0
                )
            ) as session:

                await session.post(
                    reaction_url,
                    json=reaction_payload
                )

        except Exception:
            pass

        try:
            loading_msg = await client.send_message(
                chat_id=chat_id,
                text=(
                    f"**🔎 Searching** "
                    f"`{movie_name}` **. . .**"
                ),
                reply_to_message_id=reply_to_message_id
            )

        except Exception:
            pass

        await asyncio.sleep(1.5)

        user_id = user.id

        print(
            f"🔍 SEARCH : {movie_name}",
            flush=True
        )

        asyncio.create_task(
            increase_search_count(user_id)
        )


        # ====================================================
        # 2. YEAR DETECTION
        # ====================================================

        has_explicit_year = False
        target_year = None

        year_match = re.search(
            r"(?:^|[-\s])(\d{4})$",
            movie_name.strip()
        )

        if year_match:

            has_explicit_year = True
            target_year = year_match.group(1)


        # ====================================================
        # 3. DATABASE SEARCH
        # ====================================================

        results = await search_files(
            movie_name,
            limit=500
        )

        # Existing fallback: Movie - Year -> Movie
        if not results and "-" in movie_name:
            clean_name = (
                movie_name
                .split("-")[0]
                .strip()
            )

            if clean_name:
                results = await search_files(
                    clean_name,
                    limit=500
                )


        # ====================================================
        # 4. STRICT YEAR FILTER
        # ====================================================

        if (
            has_explicit_year
            and target_year
        ):
            filtered_results = []

            for f in results:
                f_name = (
                    f.get("movie_name")
                    or f.get("file_name")
                    or ""
                )
                f_year = str(f.get("year", ""))

                if (
                    target_year in f_name
                    or target_year == f_year
                ):
                    filtered_results.append(f)

            if filtered_results:
                results = filtered_results


        # ====================================================
        # 5. SEARCH LOG
        # ====================================================

        asyncio.create_task(
            log_search(
                client,
                user,
                movie_name,
                len(results) if results else 0
            )
        )


        # ====================================================
        # 6. NO DATABASE RESULTS (GOOGLE FALLBACK)
        # ====================================================

        if not results:

            google_query = urllib.parse.quote_plus(
                movie_name
            )

            google_search_url = (
                "https://www.google.com/search"
                f"?q={google_query}"
            )


            no_result_text = (
                f'✨ **Oops! I couldn\'t find '
                f'"{movie_name}" in my database** 📀\n\n'
                "🔍 **Search on Google and check "
                "if your spelling is correct.**\n\n"
                "📖 **Please read the instructions "
                "to get better results.**"
            )


            no_result_buttons = [
                [
                    InlineKeyboardButton(
                        "‼️ INSTRUCTIONS ‼️",
                        callback_data=(
                            "search_instructions"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "♻️ GOOGLE SEARCH ♻️",
                        url=google_search_url
                    )
                ]
            ]


            no_result_message = await client.send_message(
                chat_id=chat_id,
                text=no_result_text,
                reply_markup=InlineKeyboardMarkup(
                    no_result_buttons
                ),
                reply_to_message_id=reply_to_message_id
            )

            if no_result_message:
                asyncio.create_task(
                    auto_delete_message(
                        no_result_message,
                        delay_seconds=40
                    )
                )

            return


        # ====================================================
        # 7. SEARCH METRICS & AUDIO DETECTION
        # ====================================================

        elapsed_sec = (
            f"{time.time() - start_time:.2f}"
        )

        total_files_count = len(results)

        user_name = (
            user.first_name or "User"
        )

        user_mention = (
            f'<a href="tg://user?id={user.id}">'
            f'<b>{html.escape(user_name)}</b>'
            f'</a>'
        )


        detected_audios = set()

        for f in results:

            langs = extract_file_languages(f)

            detected_audios.update(langs)


        priority_order = [
            "Telugu",
            "Tamil",
            "Hindi",
            "English",
            "Malayalam",
            "Kannada"
        ]


        sorted_audios = [
            l
            for l in priority_order
            if l in detected_audios
        ]


        for l in detected_audios:

            if l not in sorted_audios:
                sorted_audios.append(l)


        audio_str = (
            ", ".join(sorted_audios)
            if sorted_audios
            else "Multi"
        )


        # ====================================================
        # 8. FINAL RESULT CAPTION
        # ====================================================

        caption_lines = []

        caption_lines.append(
            f"🎬 <b>"
            f"{html.escape(movie_name.title())}"
            f"</b>\n"
        )

        caption_lines.append(
            f"🔊 <b>AUDIO :</b> "
            f"<code>{audio_str}</code>\n"
        )


        caption_lines.extend([
            f"📁 <b>TOTAL FILES :</b> "
            f"<code>{total_files_count}</code>",

            f"📝 <b>REQUESTED BY :</b> "
            f"{user_mention}",

            f"⏰ <b>RESULT IN :</b> "
            f"<code>{elapsed_sec} s</code>\n",

            "🥦 <b><i>Requested Files</i></b> 👇"
        ])


        final_caption = "\n".join(
            caption_lines
        )


        # ====================================================
        # 9. SEARCH ID & CACHE
        # ====================================================

        search_id = str(
            uuid.uuid4()
        )

        menu_timestamp = int(
            datetime.now().timestamp()
        )


        cache_files = []

        for file in results:

            if "_id" in file:
                file["_id"] = str(
                    file["_id"]
                )

            cache_files.append(file)


        asyncio.create_task(
            save_search_cache(
                search_id,
                cache_files,
                movie_name
            )
        )


        asyncio.create_task(
            update_search_state(
                search_id,
                cache_files[:PAGE_LIMIT],
                "All",
                1
            )
        )


        # ====================================================
        # 10. BUILD FILE BUTTONS
        # ====================================================

        buttons = []

        for file in cache_files[:PAGE_LIMIT]:

            buttons.append(
                [
                    build_file_button(
                        file,
                        user_id,
                        menu_timestamp
                    )
                ]
            )


        # ====================================================
        # 11. LANGUAGE BUTTONS
        # ====================================================

        buttons.extend(
            language_buttons(
                search_id=search_id,
                timestamp=menu_timestamp,
                selected="All"
            )
        )


        # ====================================================
        # 12. SEND ALL
        # ====================================================

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


        # ====================================================
        # 13. PAGINATION
        # ====================================================

        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(cache_files),
                menu_timestamp
            )
        )


        reply_markup = InlineKeyboardMarkup(
            buttons
        )


        # ====================================================
        # 14. SEND MESSAGE (TEXT ONLY)
        # ====================================================

        sent_message = await client.send_message(
            chat_id=chat_id,
            text=final_caption,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id
        )


        # ====================================================
        # 15. AUTO DELETE RESULT MENU
        # ====================================================

        if sent_message:

            asyncio.create_task(
                auto_delete_menu(
                    client=client,
                    chat_id=chat_id,
                    message_id=sent_message.id
                )
            )


        print(
            "✅ SEARCH RESULT SENT SUCCESSFULLY",
            flush=True
        )


    except Exception as e:

        print(
            f"❌ SEARCH ERROR : {e}",
            flush=True
        )

        try:

            await client.send_message(
                chat_id,
                "⚠ Something went wrong.",
                reply_to_message_id=reply_to_message_id
            )

        except Exception:
            pass


    finally:

        # ====================================================
        # DELETE LOADING MESSAGE
        # ====================================================

        if loading_msg:

            try:
                await loading_msg.delete()
            except Exception:
                pass


# ============================================================
# PRIVATE TEXT SEARCH HANDLER
# ============================================================

@app.on_message(
    filters.private
    & filters.text
    & ~filters.command([
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
    ])
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


        movie_name = (
            message.text or ""
        ).strip()


        # ====================================================
        # IGNORE BOT / FILE MESSAGES
        # ====================================================

        if (
            "Size :-" in movie_name
            or "Size:" in movie_name
            or "@CinemaVetaBot" in movie_name
            or "@mrDuDeHoLic" in movie_name
            or movie_name.startswith("📁")
            or "Results -" in movie_name
        ):
            return


        # ====================================================
        # @BOTNAME SEARCH
        # ====================================================

        if movie_name.startswith("@"):

            parts = movie_name.split()

            movie_name = " ".join(
                parts[1:]
            )


        # ====================================================
        # /SEARCH COMMAND
        # ====================================================

        if movie_name.lower().startswith(
            "/search"
        ):

            movie_name = (
                movie_name[7:]
                .strip()
            )


        if not movie_name:
            return


        # ====================================================
        # FORCE SUBSCRIBE
        # ====================================================

        if not await enforce_fsub(
            client,
            message,
            payload=movie_name
        ):
            return


        # ====================================================
        # EXECUTE SEARCH
        # ====================================================

        await execute_search(
            client=client,
            user=message.from_user,
            chat_id=message.chat.id,
            movie_name=movie_name,
            reply_to_message_id=message.id
        )


    except Exception as e:

        print(
            f"❌ SEARCH HANDLER ERROR : {e}",
            flush=True
        )

        try:

            await message.reply_text(
                "⚠️ Something went wrong.",
                quote=True
            )

        except Exception:
            pass
