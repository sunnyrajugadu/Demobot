from pyrogram import Client

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    USER_SESSION
)


# Bot client (Standard operations, inline & user commands)
app = Client(
    "CinemaVeta",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=32,
    sleep_threshold=60
)


# User client (Tuned for ultra-fast parallel chunk retrieval & raw MTProto queries)
user_app = Client(
    "CinemaVetaUser",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USER_SESSION,
    workers=64,
    sleep_threshold=300,
    max_concurrent_transmissions=20,
    no_updates=True,
    takeout=False
)
