import asyncio
import time
import html
import uuid
from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot import app
from filters.fsub import enforce_fsub
from database.models import (
    search_files,
    increase_search_count,
    save_search_cache,
    update_search_state
)
from handlers.search import (
    FIXED_LANGUAGES,
    PAGE_LIMIT,
    format_size,
    extract_file_languages,
    get_file_display_name,
    language_buttons,
    pagination_buttons,
    auto_delete_message,
    log_search,
    extract_distinct_movies
)
from utils.helpers import get_imdb_suggestions


print("✅ group.py imported", flush=True)


# ================= GROUP SEARCH EXECUTION ================= #

async def execute_group_search(
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
        print(f"🔍 GROUP SEARCH : {movie_name}", flush=True)

        asyncio.create_task(increase_search_count(user_id))

        results = await search_files(movie_name)

        if not results and "(" in movie_name:
            clean_name = movie_name.split("(")[0].strip()
            if clean_name:
                results = await search_files(clean_name)

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

        # ================= NO RESULTS ================= #
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

            no_result_msg = await client.send_message(
                chat_id=chat_id,
                text=f'✨ <b>Oops! I couldn\'t find "{movie_name}" in my database</b> 📀',
                reply_to_message_id=reply_to_message_id
            )
            if no_result_msg:
                asyncio.create_task(auto_delete_message(no_result_msg, delay_seconds=40))
            return

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

        # Exact Group Caption Style
        caption_lines = [
            f"🧿 <b>TITLE :</b> {html.escape(movie_name.title())}",
            f"📂 <b>TOTAL FILES :</b> <code>{total_files_count}</code>",
            f"🔊 <b>AUDIO :</b> <code>{audio_str}</code>",
            f"📝 <b>REQUESTED BY :</b> {user_mention}",
            f"⏰ <b>RESULT IN :</b> <code>{elapsed_sec} s</code>\n",
            "🌳 <b><i>𝑹𝒆𝒒𝒖𝒆𝒔𝒕𝒆𝒅 𝑭𝒊𝒍𝒆𝒔</i></b> 👇"
        ]

        final_caption = "\n".join(caption_lines)

        search_id = str(uuid.uuid4())
        menu_timestamp = int(datetime.now().timestamp())

        cache_files = []
        for file in results:
            if "_id" in file:
                file["_id"] = str(file["_id"])
            cache_files.append(file)

        asyncio.create_task(save_search_cache(search_id, cache_files, movie_name))
        asyncio.create_task(update_search_state(search_id, cache_files[:PAGE_LIMIT], "All", 1))

        bot_info = await client.get_me()
        bot_username = bot_info.username

        buttons = []
        for file in cache_files[:PAGE_LIMIT]:
            file_id = str(file.get("_id"))
            pm_url = f"https://t.me/{bot_username}?start=file_{file_id}"
            display_name = get_file_display_name(file)
            file_size = format_size(file.get("file_size_bytes", 0))
            buttons.append([InlineKeyboardButton(text=f"{file_size} | {display_name}", url=pm_url)])

        # Language buttons added
        buttons.extend(
            language_buttons(
                search_id=search_id,
                timestamp=menu_timestamp,
                selected="All"
            )
        )

        # "Send All" button is completely removed from here!

        # Pagination buttons added
        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(cache_files),
                menu_timestamp
            )
        )

        reply_markup = InlineKeyboardMarkup(buttons)

        sent_message = await client.send_message(
            chat_id=chat_id,
            text=final_caption,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id
        )

        if sent_message:
            asyncio.create_task(auto_delete_message(sent_message, delay_seconds=120))

        print("✅ GROUP SEARCH RESULT SENT SUCCESSFULLY", flush=True)

    except Exception as e:
        print(f"❌ GROUP SEARCH EXECUTION ERROR : {e}", flush=True)


# ================= GROUP TEXT & SEARCH HANDLER ================= #

@app.on_message(
    filters.group
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
async def group_movie_search_handler(
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

        if not movie_name or len(movie_name) < 2:
            return

        if not await enforce_fsub(client, message, payload=movie_name):
            return

        await execute_group_search(
            client=client,
            user=message.from_user,
            chat_id=message.chat.id,
            movie_name=movie_name,
            reply_to_message_id=message.id,
            allow_spelling_suggestions=True
        )

    except Exception as e:
        print(f"❌ GROUP SEARCH HANDLER ERROR : {e}", flush=True)
        try:
            await client.send_message(message.chat.id, "⚠️ Something went wrong.", reply_to_message_id=message.id)
        except Exception:
            pass
