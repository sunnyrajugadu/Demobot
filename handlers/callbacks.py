import asyncio
import html
import re
from datetime import datetime

from bson import ObjectId

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from config import (
    STORAGE_CHANNEL_ID
)

from bot import app

from database import models as db_models

from utils.logger import send_log

from utils.caption import make_file_caption

from utils.rename import clean_file_name

from utils.detectors import detect_languages

from filters.fsub import (
    is_subscribed,
    FSUB_ALERT
)

from keyboards.buttons import (
    start_buttons,
    about_buttons
)


print(
    "✅ callbacks.py imported",
    flush=True
)


# ============================================================
# SETTINGS
# ============================================================

MENU_EXPIRE_SECONDS = 300

FILES_PER_PAGE = 7

FILE_DELETE_SECONDS = 300

NOTICE_DELETE_SECONDS = 30


# ============================================================
# SIZE FORMAT
# ============================================================

def format_size(size):

    try:

        size = int(size or 0)

    except Exception:

        size = 0

    if size >= 1024 ** 3:

        return (
            f"{size / (1024 ** 3):.2f} GB"
        )

    if size >= 1024 ** 2:

        return (
            f"{size / (1024 ** 2):.2f} MB"
        )

    if size >= 1024:

        return (
            f"{size / 1024:.2f} KB"
        )

    return f"{size:.0f} B"


# ============================================================
# AUDIO FORMAT
# ============================================================

def format_audio(audio):

    if isinstance(audio, list):

        values = []

        for item in audio:

            if item:

                value = str(
                    item
                ).strip()

                if value:

                    values.append(
                        value
                    )

        if values:

            return ", ".join(
                dict.fromkeys(values)
            )

        return ""

    if audio is None:

        return ""

    audio = str(
        audio
    ).strip()

    if not audio:

        return ""

    return audio


# ============================================================
# FILE NAME FALLBACK
# ============================================================

def get_actual_file_name(file):

    """
    Always return the real filename when available.

    Priority:
    1. file_name
    2. original_file_name
    3. movie_name

    Never return literal 'Unknown'.
    """

    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or ""
    )

    cleaned = clean_file_name(
        str(raw_name)
    )

    if (
        cleaned
        and cleaned.lower() != "unknown"
    ):

        return cleaned

    original = str(
        file.get("file_name")
        or file.get("original_file_name")
        or ""
    ).strip()

    if (
        original
        and original.lower() != "unknown"
    ):

        return original

    movie_name = str(
        file.get("movie_name")
        or ""
    ).strip()

    if (
        movie_name
        and movie_name.lower() != "unknown"
    ):

        return movie_name

    return "File"


# ============================================================
# FILE DISPLAY NAME
# ============================================================

def get_file_display_name(file):
    """
    Return the complete cleaned filename.

    Used for inline file buttons.
    """

    return get_actual_file_name(
        file
    )


# ============================================================
# SEND ALL CAPTION
# ============================================================

def make_send_all_caption(file):
    """
    Caption used ONLY for Send All.

    Send All intentionally does NOT use
    make_file_caption().
    """

    file_name = get_actual_file_name(
        file
    )

    size = format_size(
        file.get(
            "file_size_bytes",
            0
        )
    )

    safe_file_name = html.escape(
        str(file_name)
    )

    safe_size = html.escape(
        str(size)
    )

    return (
        '<a href="https://t.me/CinemaVetaBot">'
        '<b>@CinemaVetaBot -</b>'
        '</a>\n'

        '<a href="https://t.me/mrDuDeHoLic">'
        '<b>@mrDuDeHoLic -</b>'
        '</a> '

        f'<b>{safe_file_name}\n'
        f'Size :- {safe_size}</b>'
    )


# ============================================================
# USER MENTION
# ============================================================

def make_user_mention(user):
    """
    Always display the user's REAL Telegram name.

    Clicking the name opens the user's Telegram profile.
    """

    display_name = (
        user.first_name
        or "User"
    )

    if user.last_name:

        display_name = (
            f"{display_name} "
            f"{user.last_name}"
        )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'<b>{html.escape(display_name)}</b>'
        f'</a>'
    )


# ============================================================
# SINGLE FILE INSTRUCTION MESSAGE
# ============================================================

def make_single_instruction_message():

    return (
        "‼️ File Delete In 5 mins\n"
        "(Due To Avoid Copyrights 😌)\n\n"

        "👉 Forward to your "
        "𝗦𝗮𝘃𝗲𝗱 𝗠𝗲𝘀𝘀𝗮𝗴𝗲𝘀 immediately 💌"
    )


# ============================================================
# SEND ALL INSTRUCTION MESSAGE
# ============================================================

def make_send_all_instruction_message(
    count
):

    return (
        f"‼️ {count} Files Delete In 5 mins\n"
        "(Due To Avoid Copyrights 😌)\n\n"

        "👉 Forward to your "
        "𝗦𝗮𝘃𝗲𝗱 𝗠𝗲𝘀𝘀𝗮𝗴𝗲𝘀 immediately 💌"
    )


# ============================================================
# SINGLE FILE DELETE MESSAGE
# ============================================================

def make_single_delete_message(user):

    mention = make_user_mention(
        user
    )

    return (
        f"𝗛𝗲𝘆 {mention},\n\n"

        "⚠️ 𝗬𝗼𝘂𝗿 𝗥𝗲𝗾𝘂𝗲𝘀𝘁 "
        "𝗛𝗮𝘀 𝗕𝗲𝗲𝗻 𝗗𝗲𝗹𝗲𝘁𝗲𝗱 👍🏻\n"

        "(Due To Avoid Copyright Issues 😌)\n\n"

        "𝗜𝗳 𝗬𝗼𝘂 𝗪𝗮𝗻𝘁 𝗧𝗵𝗮𝘁 𝗙𝗶𝗹𝗲, "
        "𝗥𝗲𝗾𝘂𝗲𝘀𝘁 𝗔𝗴𝗮𝗶𝗻 ❤️"
    )


# ============================================================
# SEND ALL DELETE MESSAGE
# ============================================================

def make_send_all_delete_message(
    user,
    count
):

    mention = make_user_mention(
        user
    )

    return (
        f"𝗛𝗲𝘆 {mention},\n\n"

        f"⚠️ 𝗬𝗼𝘂𝗿 𝗥𝗲𝗾𝘂𝗲𝘀𝘁𝗲𝗱 "
        f"{count} 𝗙𝗶𝗹𝗲𝘀 "
        "𝗛𝗮𝘃𝗲 𝗕𝗲𝗲𝗻 𝗗𝗲𝗹𝗲𝘁𝗲𝗱 👍🏻\n"

        "(Due To Avoid Copyright Issues 😌)\n\n"

        f"𝗜𝗳 𝗬𝗼𝘂 𝗪𝗮𝗻𝘁 "
        f"{'𝗧𝗵𝗼𝘀𝗲 𝗙𝗶𝗹𝗲𝘀' if count != 1 else '𝗧𝗵𝗮𝘁 𝗙𝗶𝗹𝗲'}, "
        "𝗥𝗲𝗾𝘂𝗲𝘀𝘁 𝗔𝗴𝗮𝗶𝗻 ❤️"
    )


# ============================================================
# AUTO DELETE INSTRUCTION MESSAGE (30 SECONDS)
# ============================================================

async def delete_instruction_later(
    client,
    chat_id,
    message_id
):

    try:

        await asyncio.sleep(
            NOTICE_DELETE_SECONDS
        )

        await client.delete_messages(
            chat_id=chat_id,
            message_ids=message_id
        )

    except Exception:

        pass


# ============================================================
# DELETE SINGLE SENT FILE AFTER 5 MINUTES
# ============================================================

async def delete_single_file_later(
    client,
    chat_id,
    message_id,
    user
):

    try:

        await asyncio.sleep(
            FILE_DELETE_SECONDS
        )

        deleted = False

        try:

            await client.delete_messages(
                chat_id=chat_id,
                message_ids=message_id
            )

            deleted = True

            print(
                f"🗑️ Single file deleted: "
                f"{chat_id}:{message_id}",
                flush=True
            )

        except Exception as delete_error:

            print(
                f"⚠️ Single file delete error: "
                f"{delete_error}",
                flush=True
            )

        # ====================================================
        # SEND DELETE NOTIFICATION (DELETES IN 30 SECONDS)
        # ====================================================

        if deleted:

            try:

                notice_msg = await client.send_message(
                    chat_id=chat_id,
                    text=make_single_delete_message(
                        user
                    )
                )

                if notice_msg:

                    asyncio.create_task(
                        delete_instruction_later(
                            client=client,
                            chat_id=chat_id,
                            message_id=notice_msg.id
                        )
                    )

            except Exception as notify_error:

                print(
                    f"⚠️ Single delete notification error: "
                    f"{notify_error}",
                    flush=True
                )

    except asyncio.CancelledError:

        print(
            "⚠️ Single delete task cancelled",
            flush=True
        )

        raise

    except Exception as e:

        print(
            f"❌ Single delete task error: {e}",
            flush=True
        )


# ============================================================
# DELETE SEND ALL FILES + MESSAGES AFTER 5 MINUTES
# ============================================================

async def delete_send_all_later(
    client,
    chat_id,
    message_ids,
    success_message_id,
    user,
    count
):

    try:

        await asyncio.sleep(
            FILE_DELETE_SECONDS
        )

        deleted_count = 0

        # ====================================================
        # DELETE ALL SENT FILES
        # ====================================================

        for message_id in message_ids:

            try:

                await client.delete_messages(
                    chat_id=chat_id,
                    message_ids=message_id
                )

                deleted_count += 1

                print(
                    f"🗑️ Send All file deleted: "
                    f"{chat_id}:{message_id}",
                    flush=True
                )

            except Exception as delete_error:

                print(
                    f"⚠️ Send All file delete error "
                    f"for {message_id}: "
                    f"{delete_error}",
                    flush=True
                )

        # ====================================================
        # DELETE SUCCESS MESSAGE
        # ====================================================

        if success_message_id:

            try:

                await client.delete_messages(
                    chat_id=chat_id,
                    message_ids=success_message_id
                )

                print(
                    f"🗑️ Send All success message deleted: "
                    f"{chat_id}:{success_message_id}",
                    flush=True
                )

            except Exception as success_delete_error:

                print(
                    f"⚠️ Success message delete error: "
                    f"{success_delete_error}",
                    flush=True
                )

        # ====================================================
        # SEND FINAL DELETE NOTIFICATION (DELETES IN 30 SECONDS)
        # ====================================================

        if deleted_count > 0:

            try:

                notice_msg = await client.send_message(
                    chat_id=chat_id,
                    text=make_send_all_delete_message(
                        user,
                        count
                    )
                )

                if notice_msg:

                    asyncio.create_task(
                        delete_instruction_later(
                            client=client,
                            chat_id=chat_id,
                            message_id=notice_msg.id
                        )
                    )

                print(
                    f"✅ Final Send All delete notification sent "
                    f"for {count} files",
                    flush=True
                )

            except Exception as notify_error:

                print(
                    f"⚠️ Send All notification error: "
                    f"{notify_error}",
                    flush=True
                )

    except asyncio.CancelledError:

        print(
            "⚠️ Send All delete task cancelled",
            flush=True
        )

        raise

    except Exception as e:

        print(
            f"❌ Send All delete task error: {e}",
            flush=True
        )


# ============================================================
# EXPIRY CHECK (DELETES MENU ON EXPIRY)
# ============================================================

async def check_expiry(query):

    try:

        data = query.data.split(
            ":"
        )

        if data[0] in (
            "file",
            "lang",
            "page",
            "all"
        ):

            timestamp = int(
                data[-1]
            )

            now = int(
                datetime.now().timestamp()
            )

            if (
                now - timestamp
                > MENU_EXPIRE_SECONDS
            ):

                await query.answer(
                    "This menu has expired ⏰.\n"
                    "Search again to get fresh files 🍿",
                    show_alert=True
                )

                try:

                    await query.message.delete()

                except Exception:

                    pass

                return True

    except Exception as e:

        print(
            f"⚠️ Expiry check error: {e}",
            flush=True
        )

    return False


# ============================================================
# FILE BUTTON
# ============================================================

def file_button(
    file,
    user_id,
    timestamp
):

    size = format_size(
        file.get(
            "file_size_bytes",
            0
        )
    )

    display_name = get_file_display_name(
        file
    )

    file_id = file.get(
        "_id"
    )

    return InlineKeyboardButton(
        text=(
            f"{size} | "
            f"{display_name}"
        ),
        callback_data=(
            f"file:"
            f"{user_id}:"
            f"{file_id}:"
            f"{timestamp}"
        )
    )


# ============================================================
# LANGUAGE BUTTONS
# ============================================================

def language_buttons(
    search_id,
    timestamp,
    selected=None
):

    buttons = []

    row = []

    fixed_order = [
        "All",
        "English",
        "Hindi",
        "Tamil",
        "Telugu",
        "Malayalam",
        "Kannada"
    ]

    for lang in fixed_order:

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

            buttons.append(
                row
            )

            row = []

    if row:

        buttons.append(
            row
        )

    return buttons


# ============================================================
# PAGINATION
# ============================================================

def pagination_buttons(
    search_id,
    page,
    total,
    timestamp
):

    row = []

    total_pages = (
        total + FILES_PER_PAGE - 1
    ) // FILES_PER_PAGE

    if total_pages < 1:

        total_pages = 1

    if page > 1:

        row.append(
            InlineKeyboardButton(
                "⬅️ Previous",
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


# ============================================================
# FILE ID CONVERSION
# ============================================================

def make_object_id(file_id):

    try:

        if isinstance(
            file_id,
            ObjectId
        ):

            return file_id

        if ObjectId.is_valid(
            str(file_id)
        ):

            return ObjectId(
                str(file_id)
            )

    except Exception as e:

        print(
            f"⚠️ ObjectId error: {e}",
            flush=True
        )

    return None


# ============================================================
# FIND FILE
# ============================================================

async def find_file(file_id):

    object_id = make_object_id(
        file_id
    )

    if object_id is None:

        return None

    try:

        collection = db_models.files()

        file = await collection.find_one(
            {
                "_id": object_id
            }
        )

        return file

    except Exception as e:

        print(
            f"❌ DB file lookup error: {e}",
            flush=True
        )

        return None


# ============================================================
# LANGUAGE MATCH (ENHANCED FOR MULTI-AUDIO)
# ============================================================

def file_has_language(
    file,
    language
):

    if not language:

        return False

    target_lang = str(
        language
    ).strip().lower()

    if target_lang == "all":

        return True

    languages = file.get(
        "languages",
        []
    )

    if isinstance(languages, list):

        for item in languages:

            if str(item).strip().lower() == target_lang:

                return True

    old_language = file.get(
        "language"
    )

    if old_language:

        if isinstance(old_language, list):

            for item in old_language:

                if str(item).strip().lower() == target_lang:

                    return True

        else:

            values = re.split(
                r"[+/,|]+",
                str(old_language)
            )

            for item in values:

                if item.strip().lower() == target_lang:

                    return True

    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or ""
    )

    if raw_name:

        detected = detect_languages(str(raw_name))

        for lang_name in detected:

            if lang_name.lower() == target_lang:

                return True

    return False


# ============================================================
# FILTER CACHE FILES
# ============================================================

def filter_language_files(
    files,
    language
):

    if not files:

        return []

    if (
        not language
        or language.lower() == "all"
    ):

        return list(
            files
        )

    filtered = []

    for file in files:

        if file_has_language(
            file,
            language
        ):

            filtered.append(
                file
            )

    return filtered


# ============================================================
# FORCE SUB RETRY CALLBACK
# ============================================================

@app.on_callback_query(
    filters.regex(r"^fsub_retry:(.*)")
)
async def fsub_retry_callback(
    client,
    query: CallbackQuery
):
    try:
        user_id = query.from_user.id
        raw_data = query.data.split(":", 1)[1].strip()

        # Re-check channel membership
        if not await is_subscribed(client, user_id):
            return await query.answer(
                FSUB_ALERT,
                show_alert=True
            )

        # Parse message_id and payload if packed together
        reply_to_id = None
        payload = raw_data
        if ":" in raw_data:
            parts = raw_data.split(":", 1)
            if parts[0].isdigit():
                reply_to_id = int(parts[0])
                payload = parts[1].strip()

        # Fallback to direct reply_to_message if present
        if not reply_to_id and query.message and query.message.reply_to_message:
            reply_to_id = query.message.reply_to_message.id

        await query.answer("✅ Verified! Processing request...")

        # Delete the FSub warning prompt
        try:
            await query.message.delete()
        except Exception:
            pass

        # 1. TRIGGERED FROM INLINE SEARCH FSUB
        if payload in ["inline_fsub", "fsub", "/start inline_fsub", "/start fsub"]:
            inline_launch_markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔍 Search Files Now",
                        switch_inline_query_current_chat=""
                    )
                ]
            ])
            await client.send_message(
                chat_id=user_id,
                text=(
                    "✅ <b>Joined Successful!</b>\n\n"
                    "**Click the button below to search and download files directly** 🥀"
                ),
                reply_markup=inline_launch_markup
            )
            return

        if not payload:
            await client.send_message(
                chat_id=user_id,
                text="🎉 You are now verified! Send any movie name to search."
            )
            return

        # ================= ROUTE COMMANDS ================= #
        if payload.startswith("/"):
            cmd = payload.split()[0].lower()

            dummy_msg = query.message.reply_to_message if (query.message and query.message.reply_to_message) else query.message

            if cmd == "/ping":
                from handlers.ping import ping_command
                await ping_command(client, dummy_msg)

            elif cmd == "/usage":
                from handlers.usage import usage_command
                await usage_command(client, dummy_msg)

            elif cmd == "/stats":
                from handlers.stats import stats_command
                await stats_command(client, dummy_msg)

            elif cmd == "/start":
                from handlers.start import start_command
                parts = payload.split()
                if len(parts) > 1:
                    dummy_msg.command = ["start", parts[1]]
                else:
                    dummy_msg.command = ["start"]
                await start_command(client, dummy_msg)

            else:
                await client.send_message(
                    chat_id=user_id,
                    text=f"✅ Verified! Send `{payload}` again."
                )

        else:
            # ================= EXECUTE SEARCH WITH DIRECT QUOTE REPLY ================= #
            from handlers.search import execute_search
            await execute_search(
                client=client,
                user=query.from_user,
                chat_id=user_id,
                movie_name=payload,
                reply_to_message_id=reply_to_id,
                allow_spelling_suggestions=True
            )

    except Exception as e:
        print(f"❌ FSUB RETRY CALLBACK ERROR: {e}", flush=True)
        try:
            await query.answer("❌ Verification check failed.", show_alert=True)
        except Exception:
            pass


# ============================================================
# HOME / ABOUT
# ============================================================

@app.on_callback_query(
    filters.regex(r"^home_(?:main|about)$")
)
async def home_about_callback(
    client,
    query: CallbackQuery
):
    """Handle About and Home navigation."""

    try:

        me = await client.get_me()

        bot_name = (
            me.first_name
            or me.username
            or "Bot"
        )

        bot_name = html.escape(
            bot_name
        )

        # ====================================================
        # ABOUT
        # ====================================================

        if query.data == "home_about":

            about_text = (
                f"✯ <b>𝐁𝐨𝐭 𝐍𝐚𝐦𝐞:</b> {bot_name}\n"
                '✯ <b>𝐂𝐫𝐞𝐚𝐭𝐨𝐫 :</b> '
                '<a href="https://t.me/mrDuDeHoLic">'
                '<b>mrDuDeHoLic</b>'
                '</a>\n\n'
                "📝 ʟᴀɴɢᴜᴀɢᴇ : Python\n\n"
                "📡 ʜᴏsᴛᴇᴅ ᴏɴ : VPS\n\n"
                "🌟 ᴠᴇʀsɪᴏɴ : 1.0"
            )

            await query.message.edit_caption(
                caption=about_text,
                reply_markup=about_buttons()
            )

            await query.answer()
            return

        # ====================================================
        # HOME
        # ====================================================

        user = query.from_user

        home_caption = (
            f"**🎬✨ Hey {user.mention}! 👋\n\n"
            "✨ Welcome to CinemaVeta 🍿🔥\n\n"
            "🔍 Search your favorite Movies & Series\n\n"
            "💭 Just type the movie name and get files instantly** 🚀\n\n"
        )

        await query.message.edit_caption(
            caption=home_caption,
            reply_markup=start_buttons()
        )

        await query.answer()

    except Exception as e:

        print(
            f"❌ HOME/ABOUT ERROR: {e}",
            flush=True
        )

        try:
            await query.answer(
                "❌ Unable to open this menu",
                show_alert=True
            )
        except Exception:
            pass


# ============================================================
# SEND SINGLE FILE
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^file:"
    )
)
async def send_file(
    client,
    query: CallbackQuery
):

    try:

        if await check_expiry(
            query
        ):

            return

        parts = query.data.split(
            ":"
        )

        if len(parts) != 4:

            return await query.answer(
                "❌ Invalid file button",
                show_alert=True
            )

        _, user_id, file_id, timestamp = (
            parts
        )

        user_id = int(
            user_id
        )

        # ====================================================
        # USER CHECK
        # ====================================================

        if query.from_user.id != user_id:

            return await query.answer(
                "⚠️ This button is not for you",
                show_alert=True
            )

        # ====================================================
        # FIND FILE
        # ====================================================

        file = await find_file(
            file_id
        )

        if not file:

            return await query.answer(
                "❌ File not found in database",
                show_alert=True
            )

        # ====================================================
        # SINGLE FILE CAPTION
        # ====================================================

        caption = make_file_caption(
            file
        )

        channel_id = file.get(
            "channel_id"
        )

        message_id = file.get(
            "message_id"
        )

        if not channel_id:

            return await query.answer(
                "❌ Storage channel missing",
                show_alert=True
            )

        if not message_id:

            return await query.answer(
                "❌ Message ID missing",
                show_alert=True
            )

        # ====================================================
        # COPY FILE (DIRECT TO USER PRIVATE CHAT)
        # ====================================================

        sent_message = await client.copy_message(
            chat_id=user_id,
            from_chat_id=channel_id,
            message_id=int(
                message_id
            ),
            caption=caption
        )

        # ====================================================
        # SEPARATE INSTRUCTION MESSAGE (DELETES IN 30s)
        # ====================================================

        if sent_message:

            instruction_msg = await client.send_message(
                chat_id=user_id,
                text=make_single_instruction_message()
            )

            if instruction_msg:

                asyncio.create_task(
                    delete_instruction_later(
                        client=client,
                        chat_id=user_id,
                        message_id=instruction_msg.id
                    )
                )

        # ====================================================
        # ANSWER CALLBACK
        # ====================================================

        await query.answer(
            "File Sent ✅"
        )

        # ====================================================
        # AUTO DELETE FILE TASK (DELETES IN 5 MINS)
        # ====================================================

        if sent_message:

            asyncio.create_task(
                delete_single_file_later(
                    client=client,
                    chat_id=user_id,
                    message_id=sent_message.id,
                    user=query.from_user
                )
            )

        # ====================================================
        # LOG
        # ====================================================

        try:

            await send_log(
                f"""
⬇️ <b>File Downloaded</b>

👤 User:
<code>{user_id}</code>

📒 File:
<code>{html.escape(get_actual_file_name(file))}</code>

📍 Chat:
<code>{user_id}</code>

⏱ Auto Delete:
<code>5 Minutes</code>
"""
            )

        except Exception as log_error:

            print(
                f"⚠️ Single file log error: "
                f"{log_error}",
                flush=True
            )

    except Exception as e:

        import traceback

        print(
            "❌ FILE ERROR:",
            repr(e),
            flush=True
        )

        traceback.print_exc()

        try:

            await query.answer(
                "❌ Something went wrong",
                show_alert=True
            )

        except Exception:

            pass


# ============================================================
# LANGUAGE FILTER
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^lang:"
    )
)
async def language_filter(
    client,
    query: CallbackQuery
):

    try:

        if await check_expiry(
            query
        ):

            return

        parts = query.data.split(
            ":"
        )

        if len(parts) != 4:

            return await query.answer(
                "❌ Invalid language button",
                show_alert=True
            )

        _, language, search_id, timestamp = (
            parts
        )

        # ====================================================
        # GET CACHE
        # ====================================================

        cache = await db_models.get_search_cache(
            search_id
        )

        if not cache:

            return await query.answer(
                "❌ Search expired",
                show_alert=True
            )

        # ====================================================
        # ORIGINAL FILES
        # ====================================================

        original_files = cache.get(
            "files",
            []
        )

        # ====================================================
        # FILTER
        # ====================================================

        results = filter_language_files(
            original_files,
            language
        )

        if not results:

            return await query.answer(
                f"😿 No {language} files found",
                show_alert=True
            )

        # ====================================================
        # FIRST PAGE
        # ====================================================

        current_files = results[
            :FILES_PER_PAGE
        ]

        # ====================================================
        # SAVE STATE
        # ====================================================

        await db_models.update_search_state(
            search_id,
            current_files,
            language,
            1
        )

        # ====================================================
        # BUILD MENU
        # ====================================================

        buttons = []

        for file in current_files:

            buttons.append(
                [
                    file_button(
                        file,
                        query.from_user.id,
                        timestamp
                    )
                ]
            )

        # ====================================================
        # LANGUAGE BUTTONS
        # ====================================================

        buttons.extend(
            language_buttons(
                search_id,
                timestamp,
                language
            )
        )

        # ====================================================
        # SEND ALL
        # ====================================================

        buttons.append(
            [
                InlineKeyboardButton(
                    "📤 Send All",
                    callback_data=(
                        f"all:"
                        f"{query.from_user.id}:"
                        f"{search_id}:"
                        f"{timestamp}"
                    )
                )
            ]
        )

        # ====================================================
        # PAGINATION
        # ====================================================

        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(results),
                timestamp
            )
        )

        # ====================================================
        # UPDATE MESSAGE
        # ====================================================

        await query.message.edit_reply_markup(
            InlineKeyboardMarkup(
                buttons
            )
        )

        await query.answer(
            f"✅ {language} selected"
        )

    except Exception as e:

        print(
            f"❌ LANGUAGE ERROR: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Language filter error",
                show_alert=True
            )

        except Exception:

            pass


# ============================================================
# PAGINATION
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^page:"
    )
)
async def pagination(
    client,
    query: CallbackQuery
):

    try:

        if await check_expiry(
            query
        ):

            return

        parts = query.data.split(
            ":"
        )

        if len(parts) != 4:

            return await query.answer(
                "❌ Invalid page button",
                show_alert=True
            )

        _, search_id, page, timestamp = parts

        page = int(
            page
        )

        # ====================================================
        # GET CACHE
        # ====================================================

        cache = await db_models.get_search_cache(
            search_id
        )

        if not cache:

            return await query.answer(
                "❌ Search expired",
                show_alert=True
            )

        # ====================================================
        # SELECTED LANGUAGE
        # ====================================================

        language = cache.get(
            "selected_language",
            "All"
        )

        # ====================================================
        # ORIGINAL FILES
        # ====================================================

        original_files = cache.get(
            "files",
            []
        )

        # ====================================================
        # FILTER
        # ====================================================

        files = filter_language_files(
            original_files,
            language
        )

        if not files:

            return await query.answer(
                "❌ No files found",
                show_alert=True
            )

        # ====================================================
        # PAGE RANGE
        # ====================================================

        start = (
            page - 1
        ) * FILES_PER_PAGE

        end = (
            start
            + FILES_PER_PAGE
        )

        results = files[
            start:end
        ]

        if not results:

            return await query.answer(
                "❌ No files on this page",
                show_alert=True
            )

        # ====================================================
        # SAVE STATE
        # ====================================================

        await db_models.update_search_state(
            search_id,
            results,
            language,
            page
        )

        # ====================================================
        # BUILD FILE BUTTONS
        # ====================================================

        buttons = []

        for file in results:

            buttons.append(
                [
                    file_button(
                        file,
                        query.from_user.id,
                        timestamp
                    )
                ]
            )

        # ====================================================
        # LANGUAGE BUTTONS
        # ====================================================

        buttons.extend(
            language_buttons(
                search_id,
                timestamp,
                language
            )
        )

        # ====================================================
        # SEND ALL
        # ====================================================

        buttons.append(
            [
                InlineKeyboardButton(
                    "📤 Send All",
                    callback_data=(
                        f"all:"
                        f"{query.from_user.id}:"
                        f"{search_id}:"
                        f"{timestamp}"
                    )
                )
            ]
        )

        # ====================================================
        # PAGINATION
        # ====================================================

        buttons.extend(
            pagination_buttons(
                search_id,
                page,
                len(files),
                timestamp
            )
        )

        # ====================================================
        # UPDATE MENU
        # ====================================================

        await query.message.edit_reply_markup(
            InlineKeyboardMarkup(
                buttons
            )
        )

        await query.answer()

    except Exception as e:

        print(
            f"❌ PAGINATION ERROR: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Pagination error",
                show_alert=True
            )

        except Exception:

            pass


# ============================================================
# SEND ALL FILES (EXACT CURRENT PAGE ONLY)
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^all:"
    )
)
async def send_all_files(
    client,
    query: CallbackQuery
):

    try:

        if await check_expiry(
            query
        ):

            return

        parts = query.data.split(
            ":"
        )

        if len(parts) != 4:

            return await query.answer(
                "❌ Invalid Send All button",
                show_alert=True
            )

        _, user_id, search_id, timestamp = parts

        user_id = int(
            user_id
        )

        # ====================================================
        # USER CHECK
        # ====================================================

        if query.from_user.id != user_id:

            return await query.answer(
                "⚠️ This button is not for you",
                show_alert=True
            )

        # ====================================================
        # GET CACHE
        # ====================================================

        cache = await db_models.get_search_cache(
            search_id
        )

        if not cache:

            return await query.answer(
                "❌ Search expired",
                show_alert=True
            )

        # ====================================================
        # EXTRACT EXACT CURRENT PAGE FILES (MAX 7 PER PAGE)
        # ====================================================

        current_page = cache.get("current_page") or cache.get("page") or 1
        selected_lang = cache.get("selected_language") or "All"
        original_files = cache.get("files", [])

        # Filter by selected language
        filtered_files = filter_language_files(original_files, selected_lang)

        # Calculate exact slice for current page
        start = (int(current_page) - 1) * FILES_PER_PAGE
        end = start + FILES_PER_PAGE
        files = filtered_files[start:end]

        # Fallback to current_files if slice resulted empty
        if not files:
            files = cache.get("current_files", [])[:FILES_PER_PAGE]

        if not files:

            return await query.answer(
                "❌ No files on this page",
                show_alert=True
            )

        await query.answer(
            "📨 Sending files..."
        )

        # ====================================================
        # SENT MESSAGE IDS
        # ====================================================

        sent_message_ids = []

        count = 0

        # ====================================================
        # SEND FILES FIRST (TO USER PM)
        # ====================================================

        for file in files:

            try:

                channel_id = file.get(
                    "channel_id"
                )

                message_id = file.get(
                    "message_id"
                )

                if not channel_id:

                    print(
                        "⚠️ Send All: "
                        "channel_id missing",
                        flush=True
                    )

                    continue

                if not message_id:

                    print(
                        "⚠️ Send All: "
                        "message_id missing",
                        flush=True
                    )

                    continue

                # ====================================================
                # SEND ALL CAPTION
                # ====================================================

                caption = make_send_all_caption(
                    file
                )

                # ====================================================
                # COPY FILE
                # ====================================================

                sent_message = await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=channel_id,
                    message_id=int(
                        message_id
                    ),
                    caption=caption
                )

                # ====================================================
                # SAVE SENT MESSAGE ID
                # ====================================================

                if sent_message:

                    sent_message_ids.append(
                        sent_message.id
                    )

                    count += 1

            except Exception as file_error:

                print(
                    f"⚠️ Send All File Error: "
                    f"{file_error}",
                    flush=True
                )

                continue

        # ====================================================
        # NO FILES SENT
        # ====================================================

        if count == 0:

            return await query.message.reply_text(
                "❌ No files could be sent."
            )

        # ====================================================
        # SEARCH NAME
        # ====================================================

        search_text = (
            cache.get("movie_name")
            or cache.get("search_query")
            or cache.get("query")
            or cache.get("search")
            or "Search"
        )

        # ====================================================
        # SUCCESS MESSAGE
        # ====================================================

        success_message = await query.message.reply_text(
            f"✅ Sent {count} files for "
            f"'<b><code>{html.escape(str(search_text))}"
            f"</code></b>' "
            f"from the current page."
        )

        # ====================================================
        # COPYRIGHT INSTRUCTION MESSAGE (DELETES IN 30s)
        # ====================================================

        instruction_message = await client.send_message(
            chat_id=user_id,
            text=make_send_all_instruction_message(
                count
            )
        )

        if instruction_message:

            asyncio.create_task(
                delete_instruction_later(
                    client=client,
                    chat_id=user_id,
                    message_id=instruction_message.id
                )
            )

        # ====================================================
        # AUTO DELETE TASK (5 MINUTES)
        # ====================================================

        if sent_message_ids:

            asyncio.create_task(
                delete_send_all_later(
                    client=client,
                    chat_id=user_id,
                    message_ids=sent_message_ids,
                    success_message_id=(
                        success_message.id
                        if success_message
                        else None
                    ),
                    user=query.from_user,
                    count=count
                )
            )

        # ====================================================
        # LOG
        # ====================================================

        try:

            user = query.from_user

            first_name = (
                user.first_name
                or "User"
            )

            last_name = (
                user.last_name
                or ""
            )

            full_name = (
                f"{first_name} {last_name}"
                .strip()
            )

            username = (
                f"@{user.username}"
                if user.username
                else "N/A"
            )

            clickable_name = (
                f'<a href="tg://user?id={user.id}">'
                f'{html.escape(full_name)}'
                f'</a>'
            )

            # ====================================================
            # FILE DETAILS
            # ====================================================

            file_lines = []

            for index, file in enumerate(
                files,
                start=1
            ):

                file_name = get_actual_file_name(
                    file
                )

                movie_name = str(
                    file.get("movie_name")
                    or ""
                ).strip()

                if (
                    not movie_name
                    or movie_name.lower() == "unknown"
                ):

                    movie_name = file_name

                year = str(
                    file.get("year")
                    or ""
                ).strip()

                if (
                    not year
                    or year.lower() == "unknown"
                ):

                    year = ""

                quality = str(
                    file.get("quality")
                    or ""
                ).strip()

                if (
                    not quality
                    or quality.lower() == "unknown"
                ):

                    quality = ""

                audio = format_audio(
                    file.get("audio")
                )

                if audio.lower() == "unknown":

                    audio = ""

                title_parts = [
                    str(movie_name)
                ]

                if year:

                    title_parts.append(
                        year
                    )

                if quality:

                    title_parts.append(
                        quality
                    )

                if audio:

                    title_parts.append(
                        audio
                    )

                display_title = " • ".join(
                    title_parts
                )

                file_lines.append(
                    f"{index}. "
                    f"{html.escape(display_title)}\n"
                    f"   📄 "
                    f"{html.escape(str(file_name))}"
                )

            files_text = "\n".join(
                file_lines
            )

            # ====================================================
            # SEND LOG
            # ====================================================

            log_text = (
                "📤 <b>SEND ALL USED</b>\n\n"

                "👤 <b>User Details</b>\n"
                f"Name: {clickable_name}\n"
                f"Username: {html.escape(username)}\n"
                f"User ID: <code>{user.id}</code>\n"
                f"Chat ID: <code>{user_id}</code>\n\n"

                "🔎 <b>Search</b>\n"
                f"{html.escape(str(search_text))}\n\n"

                "📦 <b>Send All Details</b>\n"
                f"Files Sent: <code>{count}</code>\n"
                f"Auto Delete: <code>5 Minutes</code>\n\n"

                "📁 <b>Files</b>\n"
                f"{files_text}"
            )

            await send_log(
                log_text
            )

        except Exception as log_error:

            print(
                f"⚠️ Send All Log Error: "
                f"{log_error}",
                flush=True
            )

    except Exception as e:

        print(
            f"❌ SEND ALL ERROR: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Error while sending files",
                show_alert=True
            )

        except Exception:

            pass


# ============================================================
# BACK SEARCH
# ============================================================

async def back_search(
    client,
    query: CallbackQuery
):

    try:

        if await check_expiry(
            query
        ):

            return

        parts = query.data.split(
            ":"
        )

        if len(parts) != 3:

            return await query.answer(
                "❌ Invalid back button",
                show_alert=True
            )

        _, search_id, timestamp = parts

        cache = await db_models.get_search_cache(
            search_id
        )

        if not cache:

            return await query.answer(
                "❌ Search expired",
                show_alert=True
            )

        selected_language = "All"

        results = cache.get(
            "files",
            []
        )

        if not results:

            return await query.answer(
                "❌ No files found",
                show_alert=True
            )

        current_files = results[
            :FILES_PER_PAGE
        ]

        await db_models.update_search_state(
            search_id,
            current_files,
            selected_language,
            1
        )

        buttons = []

        for file in current_files:

            buttons.append(
                [
                    file_button(
                        file,
                        query.from_user.id,
                        timestamp
                    )
                ]
            )

        buttons.extend(
            language_buttons(
                search_id,
                timestamp,
                selected_language
            )
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    "📤 Send All",
                    callback_data=(
                        f"all:"
                        f"{query.from_user.id}:"
                        f"{search_id}:"
                        f"{timestamp}"
                    )
                )
            ]
        )

        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(results),
                timestamp
            )
        )

        await query.message.edit_reply_markup(
            InlineKeyboardMarkup(
                buttons
            )
        )

        await query.answer(
            "↩️️ All languages selected"
        )

    except Exception as e:

        print(
            f"❌ BACK ERROR: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Error",
                show_alert=True
            )

        except Exception:

            pass


# ============================================================
# SPELLING SUGGESTION SELECTION CALLBACK
# ============================================================

@app.on_callback_query(
    filters.regex(r"^spell:")
)
async def spelling_suggestion_callback(
    client,
    query: CallbackQuery
):
    """
    Handles user clicking on spelling suggestion button.
    Directly triggers the search using the exact corrected title.
    """
    try:
        parts = query.data.split(":", 2)

        if len(parts) < 3:
            return await query.answer("❌ Invalid suggestion data", show_alert=True)

        _, user_id_str, selected_movie = parts

        try:
            target_user_id = int(user_id_str)
        except ValueError:
            target_user_id = query.from_user.id

        # Verify button belongs to the requester
        if query.from_user.id != target_user_id:
            return await query.answer(
                "⚠️ This suggestion button is not for you",
                show_alert=True
            )

        await query.answer(f"🔎 Searching: {selected_movie}")

        # Delete the spelling suggestions menu immediately
        try:
            await query.message.delete()
        except Exception:
            pass

        # Trigger direct search with selected title
        # allow_spelling_suggestions=False guarantees that if file is missing in DB,
        # it directly shows "Oops! I couldn't find" and auto-deletes in 10s!
        from handlers.search import execute_search

        reply_to_id = query.message.reply_to_message.id if query.message and query.message.reply_to_message else None

        await execute_search(
            client=client,
            user=query.from_user,
            chat_id=query.message.chat.id,
            movie_name=selected_movie,
            reply_to_message_id=reply_to_id,
            allow_spelling_suggestions=False
        )

    except Exception as e:
        print(f"❌ SPELL SUGGESTION CALLBACK ERROR: {e}", flush=True)
        try:
            await query.answer("❌ Failed to process movie selection", show_alert=True)
        except Exception:
            pass


# ============================================================
# CLOSE BUTTON CALLBACK
# ============================================================

@app.on_callback_query(
    filters.regex(r"^close$")
)
async def close_menu_callback(
    client,
    query: CallbackQuery
):
    """Deletes menu on close button click."""
    try:
        await query.message.delete()
        await query.answer("Closed ✖")
    except Exception:
        try:
            await query.answer()
        except Exception:
            pass


# ============================================================
# UPDATED SPELLING & FRANCHISE SELECTION CALLBACK
# ============================================================

@app.on_callback_query(
    filters.regex(r"^spell:")
)
async def spelling_suggestion_callback(
    client,
    query: CallbackQuery
):
    """
    Handles user clicking on IMDb spelling / franchise suggestion button.
    Extracts the selected movie name, cleans year brackets if needed for DB,
    and calls execute_search with allow_spelling_suggestions=False so that
    it displays the HD landscape banner and direct files.
    """
    try:
        parts = query.data.split(":", 2)

        if len(parts) < 3:
            return await query.answer("❌ Invalid suggestion data", show_alert=True)

        _, user_id_str, selected_movie = parts

        try:
            target_user_id = int(user_id_str)
        except ValueError:
            target_user_id = query.from_user.id

        # Verify button belongs to the requester
        if query.from_user.id != target_user_id:
            return await query.answer(
                "⚠️ This suggestion button is not for you",
                show_alert=True
            )

        await query.answer(f"🔎 Searching: {selected_movie}")

        # Get reply message id to link reply preview cleanly
        reply_to_id = None
        if query.message and query.message.reply_to_message:
            reply_to_id = query.message.reply_to_message.id

        # Delete the suggestions buttons menu
        try:
            await query.message.delete()
        except Exception:
            pass

        from handlers.search import execute_search

        # allow_spelling_suggestions=False guarantees that it directly fetches
        # the Landscape Banner and sends files without re-triggering suggestions
        await execute_search(
            client=client,
            user=query.from_user,
            chat_id=query.message.chat.id,
            movie_name=selected_movie,
            reply_to_message_id=reply_to_id,
            allow_spelling_suggestions=False
        )

    except Exception as e:
        print(f"❌ SPELL SUGGESTION CALLBACK ERROR: {e}", flush=True)
        try:
            await query.answer("❌ Failed to process movie selection", show_alert=True)
        except Exception:
            pass


# ============================================================
# SEARCH INSTRUCTIONS ALERT CALLBACK
# ============================================================

@app.on_callback_query(filters.regex(r"^search_instructions$"))
async def search_instructions_callback(client, query: CallbackQuery):
    alert_text = (
        "📝 MOVIE REQUEST FORMAT -\n\n"
        "Salaar OR Salaar 2023\n\n"
        "📝 TV SERIES REQUEST FORMAT -\n\n"
        "Save The Tigers OR Save The Tigers S01E01 OR Save The Tigers S01 E01\n\n"
        "DON'T USE SYMBOLS....‼️"
    )
    await query.answer(alert_text, show_alert=True)

