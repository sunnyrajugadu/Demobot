from pyrogram import Client

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    USER_SESSION_1,
    USER_SESSION_2,
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


# First User client (For parallel reindexing part 1)
user_app_1 = Client(
    "CinemaVetaUser1",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USER_SESSION_1 or USER_SESSION,
    workers=64,
    sleep_threshold=300,
    max_concurrent_transmissions=20,
    no_updates=True,
    takeout=False
)


# Second User client (For parallel reindexing part 2)
user_app_2 = Client(
    "CinemaVetaUser2",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USER_SESSION_2 or USER_SESSION,
    workers=64,
    sleep_threshold=300,
    max_concurrent_transmissions=20,
    no_updates=True,
    takeout=False
)
