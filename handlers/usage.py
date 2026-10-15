import os
import asyncio
import psutil
import aiohttp

from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from config import USAGE_VIDEO, BOT_TOKEN
from database import get_collection
from filters.fsub import enforce_fsub


BOT_START_TIME = datetime.now(
    ZoneInfo("Asia/Kolkata")
)


# ================= HELPER: GUARANTEED BLOCKQUOTE ================= #

async def edit_usage_with_quote(msg: Message, html_text: str):
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
        print(f"⚠️ Bot API usage edit fallback: {api_err}", flush=True)

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


# ================= UPTIME ================= #

def format_uptime():

    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    uptime = now - BOT_START_TIME

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

    return uptime_text


# ================= PROGRESS BAR ================= #

def progress_bar(
    percent,
    length=10
):

    percent = max(
        0,
        min(
            percent,
            100
        )
    )

    filled = int(
        percent / 100 * length
    )

    return (
        "█" * filled +
        "░" * (
            length - filled
        )
    )


# ================= STATUS ================= #

def status_icon(percent):

    if percent < 60:
        return "🟢"

    elif percent < 85:
        return "🟡"

    return "🔴"


# ================= FORMAT GIB ================= #

def format_gib(value):

    return (
        f"{value / (1024 ** 3):.2f} GiB"
    )


# ================= USAGE MESSAGE (WITH QUOTE BOX) ================= #

def build_usage_message(
    cpu,
    ram_percent,
    disk_percent,
    total,
    used,
    free,
    mongo_status,
    mongo_used_mb,
    mongo_free_mb,
    mongo_percent,
    refresh_line=None
):

    refresh_text = ""

    if refresh_line:

        refresh_text = (
            f"\n\n<b>{refresh_line}</b>"
        )

    return (
        "<blockquote><b>🧿 CINEMAVETA USAGE </b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🖥 CPU  {status_icon(cpu)}  {cpu:.1f}%</b>\n"
        f"   <b>[ {progress_bar(cpu)} ]</b>\n\n"
        f"<b>🧠 RAM  {status_icon(ram_percent)}  {ram_percent:.1f}%</b>\n"
        f"   <b>[ {progress_bar(ram_percent)} ]</b>\n\n"
        f"<b>💾 Disk  {status_icon(disk_percent)}  {disk_percent:.1f}%</b>\n"
        f"   <b>[ {progress_bar(disk_percent)} ]</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🌱 MongoDB  {mongo_status}</b>\n"
        f"<b>💿 Used   »</b> <code>{mongo_used_mb:.2f} MB</code>\n"
        f"<b>📀 Free   »</b> <code>{mongo_free_mb:.2f} MB</code>\n"
        f"<b>☢️ Usage  »</b> <code>{mongo_percent:.1f}%</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>⏰ Uptime   »</b> <code>{format_uptime()}</code>"
        f"{refresh_text}</blockquote>"
    )


# ================= USAGE COMMAND ================= #

@app.on_message(
    filters.command("usage")
)
async def usage_command(
    client,
    message: Message
):

    # ================= ONE-LINE FSUB ENFORCEMENT ================= #
    if not await enforce_fsub(client, message, payload="/usage"):
        return

    # ================= INITIAL MESSAGE (VIDEO / TEXT QUOTE REPLY) ================= #
    initial_caption = "<blockquote>✨ <b>Checking Usage...</b></blockquote>"

    if USAGE_VIDEO:
        try:
            msg = await message.reply_video(
                video=USAGE_VIDEO,
                caption=initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await edit_usage_with_quote(msg, initial_caption)
        except Exception as e:
            print(f"⚠️ Video reply failed ({e}), sending text instead...", flush=True)
            msg = await message.reply_text(
                initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await edit_usage_with_quote(msg, initial_caption)
    else:
        msg = await message.reply_text(
            initial_caption,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
        await edit_usage_with_quote(msg, initial_caption)

    # ================= DATABASE ================= #

    users = get_collection(
        "users"
    )

    db = users.database

    # ================= 30 SECOND REFRESH ================= #

    total_refresh_time = 30

    refresh_interval = 5

    for elapsed in range(
        0,
        total_refresh_time,
        refresh_interval
    ):

        try:

            # ================= CPU ================= #

            cpu = psutil.cpu_percent(
                interval=0.3
            )

            # ================= RAM ================= #

            ram = psutil.virtual_memory()

            ram_percent = ram.percent

            # ================= DISK ================= #

            disk = psutil.disk_usage(
                "/"
            )

            disk_percent = disk.percent

            total = disk.total

            used = disk.used

            free = disk.free

            # ================= MONGODB ================= #

            db_stats = await db.command(
                "dbStats"
            )

            mongo_used_bytes = (
                db_stats.get(
                    "dataSize",
                    0
                )
                +
                db_stats.get(
                    "indexSize",
                    0
                )
            )

            mongo_used_mb = (
                mongo_used_bytes /
                (1024 ** 2)
            )

            # MongoDB Free Tier 512 MB
            mongo_total_mb = 512

            mongo_free_mb = max(
                mongo_total_mb -
                mongo_used_mb,
                0
            )

            mongo_percent = (
                mongo_used_mb /
                mongo_total_mb
            ) * 100

            mongo_status = status_icon(
                mongo_percent
            )

            # ================= COUNTDOWN ================= #

            remaining = (
                total_refresh_time -
                elapsed
            )

            refresh_line = (
                f"⏱️ Auto stops in {remaining}s "
                f"• Refreshes every 5s"
            )

            # ================= UPDATE (CAPTION OR TEXT) ================= #

            updated_text = build_usage_message(
                cpu=cpu,
                ram_percent=ram_percent,
                disk_percent=disk_percent,
                total=total,
                used=used,
                free=free,
                mongo_status=mongo_status,
                mongo_used_mb=mongo_used_mb,
                mongo_free_mb=mongo_free_mb,
                mongo_percent=mongo_percent,
                refresh_line=refresh_line
            )

            await edit_usage_with_quote(msg, updated_text)

            # ================= WAIT ================= #

            await asyncio.sleep(
                refresh_interval
            )

        except Exception as e:

            print(
                f"⚠️ Usage Error: {e}",
                flush=True
            )

            break

    # ================= FINAL UPDATE ================= #

    try:

        # Get final values
        cpu = psutil.cpu_percent(
            interval=0.3
        )

        ram = psutil.virtual_memory()

        ram_percent = ram.percent

        disk = psutil.disk_usage(
            "/"
        )

        disk_percent = disk.percent

        total = disk.total

        used = disk.used

        free = disk.free

        # Final MongoDB stats
        db_stats = await db.command(
            "dbStats"
        )

        mongo_used_bytes = (
            db_stats.get(
                "dataSize",
                0
            )
            +
            db_stats.get(
                "indexSize",
                0
            )
        )

        mongo_used_mb = (
            mongo_used_bytes /
            (1024 ** 2)
        )

        mongo_total_mb = 512

        mongo_free_mb = max(
            mongo_total_mb -
            mongo_used_mb,
            0
        )

        mongo_percent = (
            mongo_used_mb /
            mongo_total_mb
        ) * 100

        mongo_status = status_icon(
            mongo_percent
        )

        # Final message (refresh line removed)
        final_text = build_usage_message(
            cpu=cpu,
            ram_percent=ram_percent,
            disk_percent=disk_percent,
            total=total,
            used=used,
            free=free,
            mongo_status=mongo_status,
            mongo_used_mb=mongo_used_mb,
            mongo_free_mb=mongo_free_mb,
            mongo_percent=mongo_percent,
            refresh_line=None
        )

        await edit_usage_with_quote(msg, final_text)

    except Exception as e:

        print(
            f"⚠️ Final Usage Error: {e}",
            flush=True
        )
