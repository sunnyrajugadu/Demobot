import asyncio
import os
import sys
from threading import Thread

sys.stdout.reconfigure(line_buffering=True)

from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify

IST = ZoneInfo("Asia/Kolkata")
BOT_START_TIME = datetime.now(IST)


def india_time():
    return datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")


# ================= WEB ================= #

web = Flask(__name__)


@web.route("/")
def home():
    return "Bot is Running ✅"


@web.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "bot": "CinemaVeta",
            "time": india_time()
        }
    ), 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web server starting on port {port}", flush=True)
    web.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


# ================= COMMANDS ================= #

async def set_commands(app):
    from pyrogram.types import BotCommand

    await app.set_bot_commands(
        [
            # ================= USER COMMANDS ================= #
            BotCommand("start", "Start CinemaVeta"),
            BotCommand("imdb", "Search movie or series details on IMDb"),
            BotCommand("ping", "Check bot ping"),
            BotCommand("usage", "Bot Usage"),
            BotCommand("stats", "Bot statistics"),
            BotCommand("generate_link", "Gen File Link"),
            # ================= OWNER COMMANDS ================= #
            BotCommand("owner", "Owner Commands")
        ]
    )
    print("✅ All bot commands registered", flush=True)


# ================= MAIN ================= #

async def main():
    print("🚀 Starting CinemaVeta...", flush=True)

    from bot import app, user_app
    from pyrogram import idle
    from database import connect_database, close_database
    from utils.logger import send_log
    from config import STORAGE_CHANNEL_ID, LOG_CHANNEL_ID

    # Web server thread (Render / VPS keep-alive)
    Thread(target=run_web, daemon=True).start()

    # Load all handler modules
    import handlers.start
    import handlers.search
    import handlers.owner
    import handlers.owner_menu
    import handlers.callbacks
    import handlers.broadcast
    import handlers.indexer
    import handlers.debug
    import handlers.ping
    import handlers.usage
    import handlers.stats
    import handlers.delete
    import handlers.deep_links
    import handlers.inline
    import handlers.imdb
    
    

    print("✅ Handlers Loaded", flush=True)

    # Database Initialization
    print("♻️ Connecting Database...", flush=True)
    await connect_database()

    # Start UserBot Client
    if user_app:
        try:
            if not user_app.is_connected:
                await user_app.start()
            print("✅ User session started (Parallel Engine Ready)", flush=True)
        except Exception as e:
            print(f"❌ User session error: {e}", flush=True)

    # Start Bot Client
    while True:
        try:
            await app.start()
            me = await app.get_me()

            # Channel validation
            try:
                await app.get_chat(STORAGE_CHANNEL_ID)
                print("✅ Storage channel accessible", flush=True)
            except Exception as e:
                print(f"❌ Storage error: {e}", flush=True)

            try:
                await app.get_chat(LOG_CHANNEL_ID)
                print("✅ Log channel accessible", flush=True)
            except Exception as e:
                print(f"❌ Log error: {e}", flush=True)

            print("========== BOT INFO ==========", flush=True)
            print(f"ID: {me.id}", flush=True)
            print(f"USERNAME: @{me.username}", flush=True)
            print(f"NAME: {me.first_name}", flush=True)
            print("==============================", flush=True)

            await set_commands(app)

            await send_log(
                f"🟢 <b>Status</b>: Online\n"
                f"👤 <b>Username:</b> @{me.username}\n"
                f"🏷 <b>Name:</b> {me.first_name}"
            )

            print("🔥 Bot is Running — waiting for messages...", flush=True)
            await idle()
            break

        except Exception as e:
            print(f"🚨 BOT CRASH : {e}", flush=True)
            try:
                await send_log(
                    f"🚨 <b>CinemaVeta Bot Crash</b>\n\n"
                    f"⚠️ <b>Status:</b> Offline\n"
                    f"❌ <b>Error:</b> <code>{type(e).__name__}: {e}</code>\n\n"
                    f"♻️ Restarting..."
                )
            except Exception:
                pass
            await asyncio.sleep(5)

        finally:
            if app.is_connected:
                await app.stop()

    # Graceful shutdown cleanup
    if user_app and user_app.is_connected:
        await user_app.stop()
    await close_database()


# ================= RUN ================= #

if __name__ == "__main__":
    print("MAIN FILE EXECUTED", flush=True)
    asyncio.run(main())
