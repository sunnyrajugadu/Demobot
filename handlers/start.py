from datetime import datetime
from zoneinfo import ZoneInfo
import aiohttp

from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from config import STATS_VIDEO, BOT_TOKEN
from database import get_collection
from filters.fsub import enforce_fsub


# ============================================================
# BOT START TIME
# ============================================================

BOT_START_TIME = datetime.now(
    ZoneInfo("Asia/Kolkata")
)


# ============================================================
# HELPER: GUARANTEED BLOCKQUOTE FOR VIDEO CAPTION & TEXT
# ============================================================

async def edit_stats_with_quote(msg: Message, html_text: str):
    """Edits video caption or text via Telegram Bot API so <blockquote> always renders."""
    is_media = bool(msg.video or msg.photo or msg.document or msg.animation)
    method = "editMessageCaption" if is_media else "editMessageText"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    payload = {
        "chat_id": msg.chat.id,
        "message_id": msg.id,
        "parse_mode": "HTML"
    }
    if is_media:
        payload["caption"] = html_text
    else:
        payload["text"] = html_text

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
            async with session.post(api_url, json=payload) as resp:
                res = await resp.json(content_type=None)
                if resp.status == 200 and res.get("ok"):
                    return
    except Exception as api_err:
        print(f"⚠️ Bot API stats edit fallback: {api_err}", flush=True)

    if is_media:
        await msg.edit_caption(
            caption=html_text,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        await msg.edit_text(
            text=html_text,
            parse_mode=enums.ParseMode.HTML
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
    initial_caption = "<blockquote>✨ <b>Checking Stats...</b></blockquote>"

    if STATS_VIDEO:
        try:
            msg = await message.reply_video(
                video=STATS_VIDEO,
                caption=initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await edit_stats_with_quote(msg, initial_caption)
        except Exception as e:
            print(f"⚠️ Video reply failed ({e}), sending text instead...", flush=True)
            msg = await message.reply_text(
                initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await edit_stats_with_quote(msg, initial_caption)
    else:
        msg = await message.reply_text(
            initial_caption,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
        await edit_stats_with_quote(msg, initial_caption)

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
    # STATS MESSAGE FORMATTING (WITH QUOTE BOX)
    # ========================================================

    stats_text = (
        "<blockquote>📊 <b>𝖢𝗂𝗇𝖾𝗆𝖺𝖵𝖾𝗍𝖺 𝖲𝗍𝖺𝗍𝗂𝗌𝗍𝗂𝖼𝗌</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖴𝗌𝖾𝗋𝗌</b>   »   <code>{total_users}</code>\n\n"
        f"🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖥𝗂𝗅𝖾𝗌</b>   »   <code>{total_files}</code>\n\n"
        f"🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖢𝗁𝖺𝗍𝗌</b>   »   <code>{total_chats}</code>\n\n"
        f"🔷 <b>𝖳𝗈𝗍𝖺𝗅 𝖲𝗍𝗈𝗋𝖺𝗀𝖾</b>   »   <code>{format_size(total_bytes)}</code>\n\n"
        f"🔷 <b>𝖴𝗉𝗍𝗂𝗆𝖾</b>   »   <code>{uptime_text}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>"
    )

    # ========================================================
    # EDIT VIDEO CAPTION OR TEXT
    # ========================================================
    try:
        await edit_stats_with_quote(msg, stats_text)
    except Exception as e:
        print(f"⚠️ Failed to edit stats message: {e}", flush=True)
