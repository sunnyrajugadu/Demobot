import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = None
db = None


# ================= DATABASE CONNECTION ================= #

async def connect_database():
    global client, db

    # High-throughput connection pool for multi-worker pipelines
    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=100,
        minPoolSize=10,
        maxIdleTimeMS=45000,
        waitQueueTimeoutMS=10000
    )

    # Check MongoDB connection
    await client.admin.command("ping")

    # Select database
    db = client.CinemaVeta

    # Create indexes in parallel
    await create_indexes()

    print("✅ Database Connected & Optimized", flush=True)


# ================= GET DATABASE ================= #

def get_database():
    return db


# ================= GET COLLECTION ================= #

def get_collection(name):
    if db is None:
        raise RuntimeError("Database not connected")

    return db[name]


# ================= CREATE INDEXES ================= #

async def create_indexes():
    users = get_collection("users")
    files = get_collection("files")
    chats = get_collection("chats")
    searches = get_collection("searches")

    tasks = [
        # ---------------- USERS ---------------- #
        users.create_index("user_id", unique=True, background=True),

        # ---------------- CHATS ---------------- #
        chats.create_index("chat_id", unique=True, background=True),

        # ---------------- SEARCHES ---------------- #
        searches.create_index("search_id", unique=True, background=True),

        # ---------------- FILES ---------------- #
        files.create_index("file_unique_id", unique=True, background=True),
        files.create_index("movie_name", background=True),
        files.create_index("file_name", background=True),
        files.create_index([("indexed_at", -1)], background=True),
        files.create_index([("updated_at", -1)], background=True),
        files.create_index("languages", background=True),
        files.create_index("language", background=True),
        files.create_index("year", background=True),
        files.create_index("quality", background=True),
        files.create_index("thumb_url", background=True),
        files.create_index("poster_url", background=True)
    ]

    await asyncio.gather(*tasks)


# ================= CLOSE DATABASE ================= #

async def close_database():
    global client

    if client:
        client.close()
        client = None


# ================= FILE HELPERS ================= #

from .models import get_file
