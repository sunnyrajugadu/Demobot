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


# User session (ONLY for reindex)

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
    "https://ibb.co/1JMmwH4F",
    "https://ibb.co/TDPwpkhq",
    "https://ibb.co/xqLPB7vK",
    "https://ibb.co/Qjr5GnHR",
    "https://ibb.co/fV4D0wDP",
    "https://ibb.co/9f8rnnZ",
    "https://ibb.co/B00FNwR",
    "https://ibb.co/BvrJjPd",
    "https://ibb.co/sdR4ymvn",
    "https://ibb.co/TDDY1wL1",
    "https://ibb.co/ks5tQ3YX",
    "https://ibb.co/Q3j4V1nq",
    "https://ibb.co/4gwZbfCT",
    "https://ibb.co/PvmTz1Gj",
    "https://ibb.co/219nRS2c",
    "https://ibb.co/B5RjysgV",
    "https://ibb.co/tMQhnQYb",
    "https://ibb.co/bjcbzq3v",
    "https://ibb.co/Lzhwctjg",
    "https://ibb.co/jvydjGmj",
    "https://ibb.co/27BgBp38",
    "https://ibb.co/whFthTNb",
    "https://ibb.co/ch4T1HgT",
    "https://ibb.co/Qt6rKnn",
    "https://ibb.co/WpfXdhdv",
    "https://ibb.co/BKdHzVTH",
    "https://ibb.co/XxMDLQFT",
    "https://ibb.co/FLcVQ0zt",
    "https://ibb.co/vxHLtSHJ",
    "https://ibb.co/Q7v3dKS3",
    "https://ibb.co/JW6T76sk",
    "https://ibb.co/rftcmJvQ",
    "https://ibb.co/wNDYRyzx",
    "https://ibb.co/0pJx21m3",
    "https://ibb.co/SXSsgR7Q",
    "https://ibb.co/NdvTK7jp",
    "https://ibb.co/Y4YMCn7h",
    "https://ibb.co/ycZHdC4k",
    "https://ibb.co/7NBX2pnT",
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
