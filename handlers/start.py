import io
import html
import random
import asyncio
import aiohttp
from bson import ObjectId

from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from config import START_IMAGES, BOT_TOKEN
from database.models import (
    save_user,
    save_chat,
    update_activity,
    get_user,
    files
)
from keyboards.buttons import start_buttons
from utils.logger import send_log
from utils.caption import make_file_caption
from filters.fsub import enforce_fsub

print("✅ start.py imported", flush=True)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ============================================================
# HELPER: CONVERT PYROGRAM BUTTONS TO BOT API JSON
# ============================================================
def markup_to_dict(markup):
    """Converts Pyrogram InlineKeyboardMarkup to Bot API dict so buttons stay intact."""
    if not markup or not hasattr(markup, "inline_keyboard"):
        return None

    keyboard = []
    for row in markup.inline_keyboard:
        row_list = []
        for btn in row:
            b = {"text": btn.text}
            if getattr(btn, "url", None):
                b["url"] = btn.url
            if getattr(btn, "callback_data", None):
                b["callback_data"] = btn.callback_data
            if getattr(btn, "switch_inline_query", None) is not None:
                b["switch_inline_query"] = btn.switch_inline_query
            if getattr(btn, "switch_inline_query_current_chat", None) is not None:
                b["switch_inline_query_current_chat"] = btn.switch_inline_query_current_chat
            if getattr(btn, "web_app", None):
                b["web_app"] = {"url": btn.web_app.url}
            row_list.append(b)
        keyboard.append(row_list)
    return {"inline_keyboard": keyboard}


# ============================================================
# HELPER: GUARANTEED BLOCKQUOTE FOR START PHOTO & TEXT
# ============================================================
async def send_or_edit_start_blockquote(
    chat_id: int,
    reply_to_message_id: int,
    html_text: str,
    reply_markup=None,
    photo_url: str = None,
    existing_msg: Message = None
) -> bool:
    """Uses Telegram Bot API directly so <blockquote> renders on the very first /start."""
    markup_dict = markup_to_dict(reply_markup)

    # Case 1: Edit an already-sent Pyrogram message (e.g. stream buffer fallback)
    if existing_msg is not None:
        is_media = bool(existing_msg.photo or existing_msg.video or existing_msg.document or existing_msg.animation)
        method = "editMessageCaption" if is_media else "editMessageText"
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

        payload = {
            "chat_id": chat_id,
            "message_id": existing_msg.id,
            "parse_mode": "HTML"
        }
        if is_media:
            payload["caption"] = html_text
        else:
            payload["text"] = html_text

        if markup_dict:
            payload["reply_markup"] = markup_dict

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
                async with session.post(api_url, json=payload) as resp:
                    res = await resp.json(content_type=None)
                    if resp.status == 200 and res.get("ok"):
                        return True
        except Exception as e:
            print(f"⚠️ Bot API start edit fallback error: {e}", flush=True)
        return False

    # Case 2: Send brand-new Photo or Text directly via Bot API with <blockquote>
    method = "sendPhoto" if photo_url else "sendMessage"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    payload = {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "parse_mode": "HTML"
    }
    if photo_url:
        payload["photo"] = photo_url
        payload["caption"] = html_text
    else:
        payload["text"] = html_text

    if markup_dict:
        payload["reply_markup"] = markup_dict

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
            async with session.post(api_url, json=payload) as resp:
                res = await resp.json(content_type=None)
                if resp.status == 200 and res.get("ok"):
                    return True
    except Exception as e:
        print(f"⚠️ Bot API direct send failed ({e})", flush=True)

    return False


async def download_image_stream(url: str) -> io.BytesIO | None:
    """Fallback to stream into RAM if Telegram fails to download directly from the URL."""
    try:
        async with aiohttp.ClientSession(
            headers=HTTP_HEADERS,
            timeout=aiohttp.ClientTimeout(total=2.0)
        ) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if data:
                        bio = io.BytesIO(data)
                        bio.name = "start_image.jpg"
                        return bio
    except Exception:
        pass
    return None


async def process_user_db(user_id: int, username: str, chat_id: int, chat_type: str):
    """Executes DB updates & logs in background so /start responds without DB delay."""
    try:
        existing = await get_user(user_id)
        is_new = existing is None

        await save_user(user_id, username)
        await update_activity(user_id)
        await save_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id
        )

        if is_new:
            await send_log(
                f"📈 <b>New User Started Bot</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"👤 Username: @{username if username else 'No Username'}\n"
                f"⚡ Action: START"
            )
    except Exception as e:
        print(f"[start bg task] error: {e}", flush=True)


# ============================================================
# /START HANDLER (PRIVATE ONLY)
# ============================================================
@app.on_message(filters.private & filters.command("start"))
async def start_command(client, message: Message):
    print("START HANDLER CALLED", flush=True)
    user = message.from_user

    if not user:
        return

    # ========================================================
    # 1. REACT TO USER'S /START COMMAND FIRST
    # ========================================================
    try:
        reaction_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
        reaction_payload = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "reaction": [{"type": "emoji", "emoji": "💋"}],
            "is_big": True
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.0)) as session:
            async with session.post(reaction_url, json=reaction_payload) as response:
                result = await response.json(content_type=None)
                if response.status == 200 and result.get("ok"):
                    print("💋 START MESSAGE REACTION SENT", flush=True)
                else:
                    print(f"⚠ START REACTION FAILED: {result}", flush=True)
    except Exception as e:
        print(f"⚠️ START REACTION FAILED: {e}", flush=True)

    # Reaction motham pop up avvadaniki 1.5 seconds delay (tharuvaathe start msg vasthundi)
    await asyncio.sleep(1.5)

    # ====================================================
    # Background task for database and logging
    # ====================================================
    asyncio.create_task(
        process_user_db(
            user_id=user.id,
            username=user.username,
            chat_id=message.chat.id,
            chat_type=message.chat.type.value
        )
    )

    # ====================================================
    # PAYLOAD / DEEP LINK CHECK
    # ====================================================
    if len(message.command) > 1:
        payload = message.command[1].strip()

        # =================================================
        # 1. INLINE FSUB TRIGGER
        # =================================================
        if payload in ["inline_fsub", "fsub"]:
            if not await enforce_fsub(client, message, payload=f"/start {payload}"):
                return

            return await message.reply_text(
                "✅ <b>You have joined all required channels!</b>\n\n"
                "You can now use Inline search freely.",
                reply_markup=start_buttons(),
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )

        # =================================================
        # 2. FILE DEEP LINK
        # =================================================
        if payload.startswith("file_"):
            if not await enforce_fsub(client, message, payload=f"/start {payload}"):
                return

            file_id = payload.replace("file_", "", 1).strip()

            # ObjectId validation
            try:
                object_id = ObjectId(file_id)
            except Exception:
                return await message.reply_text("❌ Invalid file link.", quote=True)

            # Find file in database
            try:
                file = await files().find_one({"_id": object_id})
            except Exception as e:
                print(f"[start] File lookup error: {e}", flush=True)
                return await message.reply_text("❌ Unable to find the file.", quote=True)

            if not file:
                return await message.reply_text("❌ File not found.", quote=True)

            # Click logging in background
            try:
                file_name = file.get("file_name") or "Unknown File"
                file_size = file.get("file_size_bytes") or 0
                movie_name = file.get("movie_name") or "Unknown"

                if isinstance(file_size, (int, float)):
                    if file_size >= 1024 ** 3:
                        size_text = f"{file_size / (1024 ** 3):.2f} GB"
                    elif file_size >= 1024 ** 2:
                        size_text = f"{file_size / (1024 ** 2):.2f} MB"
                    elif file_size >= 1024:
                        size_text = f"{file_size / 1024:.2f} KB"
                    else:
                        size_text = f"{file_size} B"
                else:
                    size_text = str(file_size)

                username = f"@{user.username}" if user.username else "No Username"
                safe_log_name = html.escape(user.first_name or "User")
                log_mention = f'<a href="tg://user?id={user.id}">{safe_log_name}</a>'

                asyncio.create_task(
                    send_log(
                        f"🔗 <b>FILE LINK CLICKED</b>\n\n"
                        f"👤 <b>User:</b> {log_mention}\n"
                        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                        f"👤 <b>Username:</b> {username}\n\n"
                        f"🎬 <b>Movie:</b> {movie_name}\n"
                        f"📒 <b>File:</b> {file_name}\n"
                        f"📪 <b>Size:</b> {size_text}\n\n"
                        f"🆔 <b>File ID:</b> <code>{file_id}</code>\n\n"
                        f"⚡ <b>Action:</b> FILE LINK CLICK"
                    )
                )
            except Exception as e:
                print(f"[start] File log warning: {e}", flush=True)

            # Channel information & Copy File
            channel_id = file.get("channel_id")
            message_id = file.get("message_id")

            if not channel_id or not message_id:
                return await message.reply_text("❌ File information is incomplete.", quote=True)

            try:
                caption = make_file_caption(file)
            except Exception:
                caption = None

            try:
                await client.copy_message(
                    chat_id=user.id,
                    from_chat_id=channel_id,
                    message_id=int(message_id),
                    caption=caption
                )
                return
            except Exception as e:
                print(f"[start] File send error: {e}", flush=True)
                return await message.reply_text("❌ Unable to send the file.", quote=True)

    # ========================================================
    # NORMAL /START MESSAGE (WITH GUARANTEED BLOCKQUOTE)
    # ========================================================
    safe_name = html.escape(user.first_name or "User")
    html_mention = f'<a href="tg://user?id={user.id}">{safe_name}</a>'

    caption = (
        f"<blockquote><b>🎬✨ Hey {html_mention}! 👋\n\n"
        "✨ Welcome to CinemaVeta 🍿🔥\n\n"
        "🔍 Search your favorite Movies & Series\n\n"
        "💭 Just type the movie name and get files instantly 🚀</b></blockquote>"
    )

    buttons = start_buttons()

    # If config list is empty, send text message with blockquote via Bot API
    if not START_IMAGES:
        sent_ok = await send_or_edit_start_blockquote(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
            html_text=caption,
            reply_markup=buttons
        )
        if sent_ok:
            return

        msg = await message.reply_text(
            text=caption,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
        await send_or_edit_start_blockquote(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
            html_text=caption,
            reply_markup=buttons,
            existing_msg=msg
        )
        return

    selected_url = random.choice(START_IMAGES)

    # 1. Direct Telegram Bot API Media Dispatch (Renders <blockquote> on 1st try!)
    sent_photo_ok = await send_or_edit_start_blockquote(
        chat_id=message.chat.id,
        reply_to_message_id=message.id,
        html_text=caption,
        reply_markup=buttons,
        photo_url=selected_url
    )
    if sent_photo_ok:
        print("⚡ INSTANT CONFIG PHOTO SENT WITH BLOCKQUOTE", flush=True)
        return

    # 1B. Pyrogram Direct Photo + Bot API Edit Fallback
    try:
        msg = await message.reply_photo(
            photo=selected_url,
            caption=caption,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
        await send_or_edit_start_blockquote(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
            html_text=caption,
            reply_markup=buttons,
            existing_msg=msg
        )
        print("⚡ INSTANT CONFIG PHOTO SENT (EDITED BLOCKQUOTE)", flush=True)
        return
    except Exception as err:
        print(f"⚠️ Direct link fetch failed ({err}), trying memory stream buffer...", flush=True)

    # 2. In-Memory Stream Fallback
    bio = await download_image_stream(selected_url)
    if bio:
        bio.seek(0)
        try:
            msg = await message.reply_photo(
                photo=bio,
                caption=caption,
                reply_markup=buttons,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await send_or_edit_start_blockquote(
                chat_id=message.chat.id,
                reply_to_message_id=message.id,
                html_text=caption,
                reply_markup=buttons,
                existing_msg=msg
            )
            print("⚡ BUFFER STREAM PHOTO SENT WITH BLOCKQUOTE", flush=True)
            return
        except Exception:
            pass

    # 3. Text fallback if image loading fails completely
    sent_text_ok = await send_or_edit_start_blockquote(
        chat_id=message.chat.id,
        reply_to_message_id=message.id,
        html_text=caption,
        reply_markup=buttons
    )
    if not sent_text_ok:
        msg = await message.reply_text(
            text=caption,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
        await send_or_edit_start_blockquote(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
            html_text=caption,
            reply_markup=buttons,
            existing_msg=msg
        )
