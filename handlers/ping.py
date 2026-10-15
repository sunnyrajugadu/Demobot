import asyncio
from time import perf_counter

from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from config import PING_VIDEO
from filters.fsub import enforce_fsub


# ================= SETTINGS ================= #

PING_TOTAL_TIME = 30
PING_REFRESH_INTERVAL = 5


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


# ================= PING MESSAGE ================= #

def build_ping_message(
    latency,
    remaining=None
):

    quality = get_ping_quality(latency)

    refresh_line = ""

    if remaining is not None:
        refresh_line = (
            f"\n\n"
            f"<i>⏱️ Auto stops in {remaining}s "
            f"• Refreshes every 5s</i>"
        )

    return f"""<blockquote>🏓 <b>Pong!</b>

<b>┌ Latency</b>  : <b>{latency:.3f} ms</b>
<b>└ Quality</b>  : <b>{quality}</b>{refresh_line}</blockquote>"""


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
            except Exception as e:
                print(f"⚠️ Video reply failed ({e}), sending text instead...", flush=True)
                msg = await message.reply_text(
                    initial_caption,
                    parse_mode=enums.ParseMode.HTML,
                    quote=True
                )
        else:
            msg = await message.reply_text(
                initial_caption,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )

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

                if msg.video:
                    await msg.edit_caption(
                        caption=new_caption,
                        parse_mode=enums.ParseMode.HTML
                    )
                else:
                    await msg.edit_text(
                        text=new_caption,
                        parse_mode=enums.ParseMode.HTML
                    )

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

            if msg.video:
                await msg.edit_caption(
                    caption=final_caption,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                await msg.edit_text(
                    text=final_caption,
                    parse_mode=enums.ParseMode.HTML
                )

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
