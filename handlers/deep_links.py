from pyrogram import filters
from pyrogram.types import Message

from bot import app
from database.models import files


print(
    "✅ deep_links.py imported",
    flush=True
)


# ============================================================
# GET MEDIA FILE UNIQUE ID
# ============================================================

def get_file_unique_id(message: Message):

    if message.document:
        return message.document.file_unique_id

    if message.video:
        return message.video.file_unique_id

    if message.audio:
        return message.audio.file_unique_id

    if message.animation:
        return message.animation.file_unique_id

    if message.photo:
        return message.photo.file_unique_id

    if message.voice:
        return message.voice.file_unique_id

    if message.video_note:
        return message.video_note.file_unique_id

    return None


# ============================================================
# FORMAT FILE SIZE
# ============================================================

def format_size(size):

    if not size:
        return "0B"

    size = int(size)

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f}GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.2f}MB"

    if size >= 1024:
        return f"{size / 1024:.2f}KB"

    return f"{size}B"


# ============================================================
# FIND FILE BY UNIQUE ID
# ============================================================

async def find_file_by_unique_id(file_unique_id):

    if not file_unique_id:
        return None

    return await files().find_one(
        {
            "file_unique_id": file_unique_id
        }
    )


# ============================================================
# /GENERATE_LINK (Deep Link Handler for PM & Group Buttons)
# ============================================================

@app.on_message(
    filters.command("start") & filters.private
)
async def pm_start_handler(
    client,
    message: Message
):
    # Check if the start command contains payload (e.g., /start file_<id>)
    if len(message.command) > 1:
        payload = message.command[1]

        if payload.startswith("file_"):
            file_id_str = payload.replace("file_", "")

            from bson import ObjectId
            try:
                file_obj_id = ObjectId(file_id_str)
            except Exception:
                return await message.reply_text(
                    "❌ Iɴᴠᴀʟɪᴅ Fɪʟᴇ Lɪɴᴋ!"
                )

            # Fetch file from database using MongoDB _id
            file_data = await files().find_one({"_id": file_obj_id})

            if not file_data:
                return await message.reply_text(
                    "❌ Fɪʟᴇ Nᴏᴛ Fᴏᴜɴᴅ Oʀ Exᴘɪʀᴇᴅ!"
                )

            # Real telegram file id or message details
            # Depending on your database model, fetch the stored telegram file_id
            tg_file_id = (
                file_data.get("file_id")
                or file_data.get("media_id")
                or file_data.get("telegram_file_id")
            )

            file_name = (
                file_data.get("file_name")
                or file_data.get("name")
                or "Uɴᴋɴᴏᴡɴ Fɪʟᴇ"
            )

            file_size = format_size(
                file_data.get("file_size")
                or file_data.get("size")
                or 0
            )

            if tg_file_id:
                try:
                    await message.reply_text(
                        f"✨ Hᴇʀᴇ Is Yᴏᴜʀ Mᴏᴠɪᴇ Fɪʟᴇ, Eɴᴊᴏʏ! 🍿"
                    )
                    # Send document directly to user PM
                    return await client.send_cached_media(
                        chat_id=message.chat.id,
                        file_id=tg_file_id,
                        caption=f"<b><code>{file_name} - [{file_size}]</code></b>"
                    )
                except Exception as e:
                    print(f"[pm_start_handler] Send media error: {e}", flush=True)

            return await message.reply_text(
                "❌ Sᴏʀʀʏ, Cᴏᴜʟᴅ Nᴏᴛ Sᴇɴᴅ Tʜᴇ Fɪʟᴇ."
            )

    # Normal /start message without payload
    await message.reply_text(
        f"👋 ʜᴇʟʟᴏ <b>{message.from_user.first_name}</b>!\n\n"
        "🎥 • Wᴇʟᴄᴏᴍᴇ Tᴏ <b>CɪɴᴇᴍᴀVᴇᴛᴀ Gʀᴏᴜᴘ Sᴇᴀʀᴄʜ</b>. 🍿\n"
        "⚡ • Sᴇᴀʀᴄʜ Yoᴜʀ Fᴀᴠᴏʀɪᴛᴇ Mᴏᴠɪᴇs & Sᴇʀɪᴇs Rɪɢʜᴛ Hᴇʀᴇ. 🎬"
    )


# ============================================================
# /GENERATE_LINK COMMAND
# ============================================================

@app.on_message(
    filters.command("generate_link")
)
async def generate_link(
    client,
    message: Message
):

    # CHECK REPLY

    if not message.reply_to_message:

        return await message.reply_text(
            "❌ Please reply to a file message "
            "and use /generate_link."
        )


    replied = message.reply_to_message


    # GET UNIQUE ID

    file_unique_id = get_file_unique_id(
        replied
    )


    if not file_unique_id:

        return await message.reply_text(
            "❌ No supported file or media found."
        )


    # FIND DATABASE FILE

    file = await find_file_by_unique_id(
        file_unique_id
    )


    if not file:

        return await message.reply_text(
            "❌ File not found in MongoDB."
        )


    # FILE ID

    file_id = str(
        file["_id"]
    )


    # GET FILE NAME

    file_name = (
        file.get("file_name")
        or file.get("name")
        or "Unknown File"
    )


    # GET FILE SIZE

    file_size = (
        file.get("file_size")
        or file.get("size")
        or 0
    )


    # FALLBACK FROM TELEGRAM MESSAGE

    if replied.document:

        file_name = (
            replied.document.file_name
            or file_name
        )

        file_size = (
            replied.document.file_size
            or file_size
        )


    elif replied.video:

        file_name = (
            replied.video.file_name
            or file_name
        )

        file_size = (
            replied.video.file_size
            or file_size
        )


    size_text = format_size(
        file_size
    )


    # GET BOT USERNAME

    try:

        bot = await client.get_me()

        bot_username = bot.username


    except Exception as e:

        print(
            f"[generate_link] Bot error: {e}",
            flush=True
        )

        return await message.reply_text(
            "❌ Unable to get bot username."
        )


    if not bot_username:

        return await message.reply_text(
            "❌ Bot username missing."
        )


    # CREATE START LINK

    link = (
        f"https://t.me/{bot_username}"
        f"?start=file_{file_id}"
    )


    # FINAL OUTPUT

    await message.reply_text(

        f"<b><code>{file_name} - [{size_text}]</code></b>\n\n"
        f"<code>{link}</code>"

    )


    print(
        f"✅ Link generated: {file_name} [{size_text}]",
        flush=True
    )
