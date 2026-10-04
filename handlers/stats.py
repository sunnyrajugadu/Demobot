from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import filters
from pyrogram.types import Message

from bot import app
from config import STATS_VIDEO
from database import get_collection
from filters.fsub import enforce_fsub


# ============================================================
# BOT START TIME
# ============================================================

BOT_START_TIME = datetime.now(
    ZoneInfo("Asia/Kolkata")
)


# ============================================================
# STATS COMMAND
# ============================================================

@app.on_message(
    filters.command("stats")
)
async def stats_command(
    client,
    message: Message
):

    # ================= ONE-LINE FSUB ENFORCEMENT ================= #
    if not await enforce_fsub(client, message, payload="/stats"):
        return

    # ================= INITIAL MESSAGE (VIDEO/TEXT QUOTE REPLY) ================= #
    initial_caption = "✨ **Checking Stats...**"

    if STATS_VIDEO:
        try:
            msg = await message.reply_video(
                video=STATS_VIDEO,
                caption=initial_caption,
                quote=True
            )
        except Exception as e:
            print(f"⚠️ Video reply failed ({e}), sending text instead...", flush=True)
            msg = await message.reply_text(
                initial_caption,
                quote=True
            )
    else:
        msg = await message.reply_text(
            initial_caption,
            quote=True
        )

    # ========================================================
    # COLLECTIONS
    # ========================================================

    users = get_collection(
        "users"
    )

    files = get_collection(
        "files"
    )

    chats = get_collection(
        "chats"
    )

    # ========================================================
    # TOTAL USERS
    # ========================================================

    total_users = await users.count_documents(
        {}
    )

    # ========================================================
    # TOTAL FILES
    # ========================================================

    total_files = await files.count_documents(
        {}
    )

    # ========================================================
    # TOTAL CHATS
    # ========================================================

    total_chats = await chats.count_documents(
        {}
    )

    # ========================================================
    # TOTAL STORAGE
    # ========================================================

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total": {
                    "$sum": "$file_size_bytes"
                }
            }
        }
    ]

    result = await files.aggregate(
        pipeline
    ).to_list(1)

    total_bytes = (
        result[0]["total"]
        if result
        else 0
    )

    # ========================================================
    # FORMAT STORAGE SIZE
    # ========================================================

    def format_size(
        size
    ):

        for unit in [
            "B",
            "KB",
            "MB",
            "GB",
            "TB"
        ]:

            if size < 1024:

                return (
                    f"{size:.2f} {unit}"
                )

            size /= 1024

        return (
            f"{size:.2f} PB"
        )

    # ========================================================
    # UPTIME
    # ========================================================

    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    uptime = (
        now - BOT_START_TIME
    )

    days = uptime.days

    hours, rem = divmod(
        uptime.seconds,
        3600
    )

    minutes, seconds = divmod(
        rem,
        60
    )

    uptime_text = (
        f"{days}d {hours}h "
        f"{minutes}m {seconds}s"
    )

    # ========================================================
    # STATS MESSAGE FORMATTING
    # ========================================================

    stats_text = f"""
📊 <b>𝖢𝗂𝗇𝖾𝗆𝖺𝖵𝖾𝗍𝖺 𝖲𝗍𝖺𝗍𝗂𝗌𝗍𝗂𝖼𝗌</b>
━━━━━━━━━━━━━━━━━━━━━━━━

🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖴𝗌𝖾𝗋𝗌</b>   »   <code>{total_users}</code>

🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖥𝗂𝗅𝖾𝗌</b>   »   <code>{total_files}</code>

🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖢𝗁𝖺𝗍𝗌</b>   »   <code>{total_chats}</code>

🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖲𝗍𝗈𝗋𝖺𝗀𝖾</b>   »   <code>{format_size(total_bytes)}</code>

🔷 <b>𝖴𝗉𝗍𝗂𝗆𝖾</b>   »   <code>{uptime_text}</code>

━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # ========================================================
    # EDIT VIDEO CAPTION OR TEXT
    # ========================================================
    try:
        if msg.video:
            await msg.edit_caption(caption=stats_text)
        else:
            await msg.edit_text(text=stats_text)
    except Exception as e:
        print(f"⚠️ Failed to edit stats message: {e}", flush=True)
