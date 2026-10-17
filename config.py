import os
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, required=True):
    value = os.getenv(key)
    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}"
        )
    return value


# ================= TELEGRAM ================= #

API_ID = int(
    get_env("API_ID")
)

API_HASH = get_env(
    "API_HASH"
)

BOT_TOKEN = get_env(
    "BOT_TOKEN"
)


# User sessions for ultra-fast parallel reindexing (2 user accounts)

USER_SESSION_1 = get_env(
    "USER_SESSION_1",
    required=False
)

USER_SESSION_2 = get_env(
    "USER_SESSION_2",
    required=False
)

# Backward compatibility fallback if someone uses single USER_SESSION
USER_SESSION = get_env(
    "USER_SESSION",
    required=False
)


# ================= DATABASE ================= #

MONGO_URI = get_env(
    "MONGO_URI"
)


# ================= CHANNELS ================= #

STORAGE_CHANNEL_ID = get_env(
    "STORAGE_CHANNEL_ID"
)

LOG_CHANNEL_ID = get_env(
    "LOG_CHANNEL_ID"
)

# Force Subscribe Channel Details
AUTH_CHANNEL = get_env("AUTH_CHANNEL")

CHANNEL_INVITE_LINK = get_env(
    "CHANNEL_INVITE_LINK"
)

# START IMAGES #
START_IMAGES = [
    "https://ibb.co/bjQS30sM",
]


# ================= PING VIDEO ================= #
PING_VIDEO = "https://www.image2url.com/r2/default/videos/1789457566226-54a75803-7c40-4972-8a95-c9b3ed87a538.mp4" 


# ================= STATS VIDEO ================= #
STATS_VIDEO = "https://www.image2url.com/r2/default/videos/1789457566226-54a75803-7c40-4972-8a95-c9b3ed87a538.mp4" 


# ================= USAGE VIDEO ================= #
USAGE_VIDEO = "https://www.image2url.com/r2/default/videos/1789457566226-54a75803-7c40-4972-8a95-c9b3ed87a538.mp4"  


# ================= OWNER ================= #

OWNER_ID = int(
    get_env("OWNER_ID")
)


# ================= GROUP ================= #

GROUP_LINK = get_env(
    "GROUP_LINK"
)


# ================= BOT ================= #

BOT_USERNAME = get_env(
    "BOT_USERNAME"
)


# ================= BOT SETTINGS ================= #

CALLBACK_TIMEOUT = 30 * 60
