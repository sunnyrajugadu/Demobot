import io
import random
import asyncio
import aiohttp
from bson import ObjectId

from pyrogram import filters
from pyrogram.types import Message

from bot import app
from config import START_IMAGES
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


print(
    "✅ start.py imported",
    flush=True
)


HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


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


async def process_user_db(
    user_id: int,
    username: str,
    chat_id: int,
    chat_type: str
):
    """Executes DB updates & logs in background so /start responds instantly without delay."""
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
                f"""
📈 <b>New User Started Bot</b>

🆔 ID: <code>{user_id}</code>
👤 Username: @{username if username else "No Username"}
⚡ Action: START
"""
            )

    except Exception as e:
        print(
            f"[start bg task] error: {e}",
            flush=True
        )


# ============================================================
# /START HANDLER (PRIVATE ONLY - INSTANT SPEED)
# ============================================================

@app.on_message(
    filters.private & filters.command("start")
)
async def start_command(
    client,
    message: Message
):
    print(
        "START HANDLER CALLED",
        flush=True
    )

    user = message.from_user

    if not user:
        return


    # ========================================================
    # 1. REACT TO USER'S /START COMMAND FIRST
    # ========================================================

    try:
        from config import BOT_TOKEN

        reaction_url = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
        )

        reaction_payload = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "reaction": [
                {
                    "type": "emoji",
                    "emoji": "💋"
                }
            ],
            "is_big": True
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3.0)
        ) as session:
            async with session.post(
                reaction_url,
                json=reaction_payload
            ) as response:

                result = await response.json(
                    content_type=None
                )

                if response.status == 200 and result.get("ok"):
                    print(
                        "💋 START MESSAGE REACTION SENT",
                        flush=True
                    )
                else:
                    print(
                        f"⚠ START REACTION FAILED: {result}",
                        flush=True
                    )

    except Exception as e:
        print(
            f"⚠️ START REACTION FAILED: {e}",
            flush=True
        )

    # Reaction motham pop up avvadaniki 1.5 seconds delay
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

        if payload in [
            "inline_fsub",
            "fsub"
        ]:

            if not await enforce_fsub(
                client,
                message,
                payload=f"/start {payload}"
            ):
                return

            return await message.reply_text(
                "✅ <b>You have joined all required channels!</b>\n\n"
                "You can now use Inline search freely.",
                reply_markup=start_buttons(),
                quote=True
            )


        # =================================================
        # 2. FILE DEEP LINK
        # =================================================

        if payload.startswith("file_"):

            if not await enforce_fsub(
                client,
                message,
                payload=f"/start {payload}"
            ):
                return


            file_id = payload.replace(
                "file_",
                "",
                1
            ).strip()


            # =================================================
            # ObjectId validation
            # =================================================

            try:
                object_id = ObjectId(file_id)

            except Exception:
                return await message.reply_text(
                    "❌ Invalid file link.",
                    quote=True
                )


            # =================================================
            # Find file in database
            # =================================================

            try:
                file = await files().find_one(
                    {
                        "_id": object_id
                    }
                )

            except Exception as e:

                print(
                    f"[start] File lookup error: {e}",
                    flush=True
                )

                return await message.reply_text(
                    "❌ Unable to find the file.",
                    quote=True
                )


            if not file:
                return await message.reply_text(
                    "❌ File not found.",
                    quote=True
                )


            # =================================================
            # Click logging in background
            # =================================================

            try:

                file_name = (
                    file.get("file_name")
                    or "Unknown File"
                )

                file_size = (
                    file.get("file_size_bytes")
                    or 0
                )

                movie_name = (
                    file.get("movie_name")
                    or "Unknown"
                )


                if isinstance(
                    file_size,
                    (int, float)
                ):

                    if file_size >= 1024 ** 3:

                        size_text = (
                            f"{file_size / (1024 ** 3):.2f} GB"
                        )

                    elif file_size >= 1024 ** 2:

                        size_text = (
                            f"{file_size / (1024 ** 2):.2f} MB"
                        )

                    elif file_size >= 1024:

                        size_text = (
                            f"{file_size / 1024:.2f} KB"
                        )

                    else:

                        size_text = (
                            f"{file_size} B"
                        )

                else:

                    size_text = str(
                        file_size
                    )


                username = (
                    f"@{user.username}"
                    if user.username
                    else "No Username"
                )


                asyncio.create_task(
                    send_log(
                        f"""
🔗 <b>FILE LINK CLICKED</b>

👤 <b>User:</b> {user.mention}
🆔 <b>ID:</b> <code>{user.id}</code>
👤 <b>Username:</b> {username}

🎬 <b>Movie:</b> {movie_name}
📒 <b>File:</b> {file_name}
📪 <b>Size:</b> {size_text}

🆔 <b>File ID:</b> <code>{file_id}</code>

⚡ <b>Action:</b> FILE LINK CLICK
"""
                    )
                )

            except Exception as e:

                print(
                    f"[start] File log warning: {e}",
                    flush=True
                )


            # =================================================
            # Channel information
            # =================================================

            channel_id = file.get(
                "channel_id"
            )

            message_id = file.get(
                "message_id"
            )


            if not channel_id or not message_id:

                return await message.reply_text(
                    "❌ File information is incomplete.",
                    quote=True
                )


            # =================================================
            # File caption
            # =================================================

            try:
                caption = make_file_caption(
                    file
                )

            except Exception:
                caption = None


            # =================================================
            # Copy file to user
            # =================================================

            try:

                await client.copy_message(
                    chat_id=user.id,
                    from_chat_id=channel_id,
                    message_id=int(message_id),
                    caption=caption
                )

                return

            except Exception as e:

                print(
                    f"[start] File send error: {e}",
                    flush=True
                )

                return await message.reply_text(
                    "❌ Unable to send the file.",
                    quote=True
                )


    # ========================================================
    # NORMAL /START MESSAGE
    # ========================================================

    caption = (
        f"**🎬✨ Hey {user.mention}! 👋\n\n"
        "✨ Welcome to CinemaVeta 🍿🔥\n\n"
        "🔍 Search your favorite Movies & Series\n\n"
        "💭 Just type the movie name and get files instantly** 🚀\n\n"
    )


    # ========================================================
    # If config list is empty, send text message
    # ========================================================

    if not START_IMAGES:

        return await message.reply_text(
            text=caption,
            reply_markup=start_buttons(),
            quote=True
        )


    selected_url = random.choice(
        START_IMAGES
    )


    # ========================================================
    # 1. Direct Telegram Media Dispatch
    # ========================================================

    try:

        await message.reply_photo(
            photo=selected_url,
            caption=caption,
            reply_markup=start_buttons(),
            quote=True
        )

        print(
            "⚡ INSTANT CONFIG PHOTO SENT",
            flush=True
        )

        return

    except Exception as err:

        print(
            f"⚠️ Direct link fetch failed ({err}), "
            f"trying memory stream buffer...",
            flush=True
        )


    # ========================================================
    # 2. In-Memory Stream Fallback
    # ========================================================

    bio = await download_image_stream(
        selected_url
    )


    if bio:

        bio.seek(0)

        try:

            await message.reply_photo(
                photo=bio,
                caption=caption,
                reply_markup=start_buttons(),
                quote=True
            )

            print(
                "⚡ BUFFER STREAM PHOTO SENT",
                flush=True
            )

            return

        except Exception:
            pass


    # ========================================================
    # 3. Text fallback if image loading fails completely
    # ========================================================

    await message.reply_text(
        text=caption,
        reply_markup=start_buttons(),
        quote=True
    )
