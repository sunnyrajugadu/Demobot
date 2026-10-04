"""
CinemaVeta Logger
All logs sent to LOG_CHANNEL_ID
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import enums

from config import LOG_CHANNEL_ID


# India Time
IST = ZoneInfo("Asia/Kolkata")


def india_time():

    return datetime.now(
        IST
    ).strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )



async def send_log(*args):
    
    from bot import app

    try:

        # Supports old calls:
        # send_log(text)
        # send_log(type, user, message, text)

        if len(args) == 1:

            text = args[0]

        else:

            text = "\n".join(
                str(x)
                for x in args
                if x is not None
            )



        await app.send_message(

            LOG_CHANNEL_ID,

            f"""
{text}
⏰ <code>{india_time()}</code>
""",

            parse_mode=enums.ParseMode.HTML

        )


    except Exception as e:

        print(
            f"[logger] send_log failed: {e}",
            flush=True
        )




async def error_log(context, error):

    try:


        await app.send_message(

            LOG_CHANNEL_ID,

            f"""
🚨 <b>CinemaVeta Error</b>

📍 <b>Context:</b>

{context}

⚠️ <b>Error:</b>

<code>{type(error).__name__}: {error}</code>

⏰ {india_time()} IST
""",

            parse_mode=enums.ParseMode.HTML

        )


    except Exception as e:

        print(
            f"[logger] error_log failed: {e}",
            flush=True
        )




async def bot_start_log(me):

    try:

        await app.send_message(

            LOG_CHANNEL_ID,

            f"""
🚀 <b>CinemaVeta Started</b>

🤖 <b>Bot:</b> @{me.username}

🆔 <b>ID:</b> {me.id}

👤 <b>Name:</b> {me.first_name}

⏰ {india_time()} IST
""",

            parse_mode=enums.ParseMode.HTML

        )


    except Exception as e:

        print(
            f"[logger] bot_start_log failed: {e}",
            flush=True
        )




async def bot_stats_log(stats):

    try:

        await app.send_message(

            LOG_CHANNEL_ID,

            f"""
{stats}
⏰ <code>{india_time()}</code>
""",

            parse_mode=enums.ParseMode.HTML

        )


    except Exception as e:

        print(
            f"[logger] bot_stats_log failed: {e}",
            flush=True
        )
