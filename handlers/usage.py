import os
import asyncio
import psutil

from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import filters
from pyrogram.types import Message

from bot import app
from config import USAGE_VIDEO
from database import get_collection
from filters.fsub import enforce_fsub


BOT_START_TIME = datetime.now(
    ZoneInfo("Asia/Kolkata")
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


# ================= USAGE MESSAGE ================= #

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
            f"\n\n**{refresh_line}**"
        )

    return f"""
**🧿 CINEMAVETA USAGE **
━━━━━━━━━━━━━━━━━━━━━━━━

**🖥 CPU  {status_icon(cpu)}  {cpu:.1f}%**
   **[ {progress_bar(cpu)} ]**

**🧠 RAM  {status_icon(ram_percent)}  {ram_percent:.1f}%**
   **[ {progress_bar(ram_percent)} ]**

**💾 Disk  {status_icon(disk_percent)}  {disk_percent:.1f}%**
   **[ {progress_bar(disk_percent)} ]**

━━━━━━━━━━━━━━━━━━━━━━━━

**🌱 MongoDB  {mongo_status}**
**💿 Used   »** `{mongo_used_mb:.2f} MB`
**📀 Free   »** `{mongo_free_mb:.2f} MB`
**☢️ Usage  »** `{mongo_percent:.1f}%`

━━━━━━━━━━━━━━━━━━━━━━━━

**⏰ Uptime   »** `{format_uptime()}`
{refresh_text}
"""


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
    initial_caption = "✨ **Checking Usage...**"

    if USAGE_VIDEO:
        try:
            msg = await message.reply_video(
                video=USAGE_VIDEO,
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

            if msg.video:
                await msg.edit_caption(caption=updated_text)
            else:
                await msg.edit_text(text=updated_text)

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

        if msg.video:
            await msg.edit_caption(caption=final_text)
        else:
            await msg.edit_text(text=final_text)

    except Exception as e:

        print(
            f"⚠️ Final Usage Error: {e}",
            flush=True
        )
