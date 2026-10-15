import asyncio
import aiohttp
from time import perf_counter

from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from config import PING_VIDEO, BOT_TOKEN
from filters.fsub import enforce_fsub


# ================= SETTINGS ================= #

PING_TOTAL_TIME = 30
PING_REFRESH_INTERVAL = 5


# ================= HELPER: GUARANTEED BLOCKQUOTE ================= #

async def edit_ping_with_quote(msg: Message, html_text: str):
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
        print(f"⚠️ Bot API ping edit fallback: {api_err}", flush=True)

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


# ================= PING QUALITY ================= #

def get_ping_quality(latency):

    if latency < 100:
        return "🟢 Excellent"
    elif latency < 300:
        return "🟡 Good"
    elif latency < 600:
        return "🟠 Fair"
    else:
        return "🔴 Poor"


# ================= PING MESSAGE (WITH QUOTE BOX) ================= #

def build_ping_message(
    latency,
    remaining=None
):

    quality = get_ping_quality(latency)

    refresh_line = ""

    if remaining is not None:
        refresh_line = (
            f"\n\n"
            f"<b>⏱️ Auto stops in {remaining}s "
            f"• Refreshes every 5s</b>"
        )

    return (
        "<blockquote>🏓 <b>Pong!</b>\n\n"
        f"┌ <b>Latency</b>  : <b>{latency:.3f} ms</b>\n"
        f"└ <b>Quality</b>  : <b>{quality}</b>"
        f"{refresh_line}</blockquote>"
    )


# ================= PING COMMAND ================= #

@app.on_message(
    filters.command("ping")
)
async def ping_command(
    client,
    message: Message
):

    try:

        # ================= ONE-LINE FSUB ENFORCEMENT ================= #
        if not await enforce_fsub(client, message, payload="/ping"):
            return

        # ================= SEND INITIAL VIDEO WITH CAPTION ================= #
        initial_caption = "<blockquote>🏓 <b>Pinging...</b></blockquote>"

        if PING_VIDEO:
            try:
                msg = await message.reply_video(
                    video=PING_VIDEO,
                    caption=initial_caption,
                    parse_mode=enums.ParseMode.HTML,
                    quote=True
                )
                await edit_ping_with_quote(msg, initial_caption)
            except Exception as e:
                print(f"⚠️ Video reply failed ({e}), sending text instead...", flush=True)
                msg = await message.reply_text(
                    initial_caption,
                    parse_mode=enums.ParseMode.HTML,
                    quote=True
                )
                await edit_ping_with_quote(msg, initial_caption)
        else:
            msg = await message.reply_text(
                initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
            await edit_ping_with_quote(msg, initial_caption)

        # ================= SETTINGS ================= #

        total_time = PING_TOTAL_TIME
        refresh_interval = PING_REFRESH_INTERVAL

        # ================= AUTO REFRESH ================= #

        for elapsed in range(
            0,
            total_time,
            refresh_interval
        ):

            try:

                # ================= MEASURE LATENCY ================= #

                start = perf_counter()
                await client.get_me()
                latency = (perf_counter() - start) * 1000

                # ================= COUNTDOWN ================= #

                remaining = total_time - elapsed
                new_caption = build_ping_message(
                    latency=latency,
                    remaining=remaining
                )

                # ================= UPDATE CAPTION / TEXT ================= #

                await edit_ping_with_quote(msg, new_caption)

            except Exception as e:

                print(
                    f"⚠️ Ping Refresh Error: {e}",
                    flush=True
                )
                break

            # ================= WAIT ================= #

            await asyncio.sleep(refresh_interval)

        # ================= FINAL REFRESH ================= #

        try:

            start = perf_counter()
            await client.get_me()
            latency = (perf_counter() - start) * 1000

            final_caption = build_ping_message(
                latency=latency,
                remaining=None
            )

            await edit_ping_with_quote(msg, final_caption)

        except Exception as e:

            print(
                f"⚠️ Final Ping Error: {e}",
                flush=True
            )

    except asyncio.CancelledError:

        pass

    except Exception as e:

        print(
            f"❌ Ping Error: {e}",
            flush=True
        )
