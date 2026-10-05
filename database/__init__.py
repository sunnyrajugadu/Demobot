import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from config import MONGO_URI

client = None
db = None


# ================= DATABASE CONNECTION ================= #

async def connect_database():
    global client, db

    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=100,
        minPoolSize=10,
        maxIdleTimeMS=45000,
        waitQueueTimeoutMS=10000
    )

    await client.admin.command("ping")
    db = client.CinemaVeta

    # IMPORTANT:
    # The old database used file_unique_id as a UNIQUE index. That is not
    # the application's duplicate rule. A Telegram file_unique_id can be
    # shared by multiple channel messages/files with different filenames.
    # The real duplicate key is EXACT filename + EXACT byte size.
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


# ================= INDEX MIGRATION ================= #

async def _drop_legacy_file_unique_index(files):
    """Remove the old unique file_unique_id index if it exists.

    This is intentionally done before creating the new duplicate index.
    MongoDB will otherwise keep failing startup with E11000 when old data
    contains the same file_unique_id more than once.
    """
    try:
        indexes = await files.index_information()
    except Exception as e:
        print(f"⚠️ Could not inspect files indexes: {e}", flush=True)
        return

    for index_name, info in indexes.items():
        key = info.get("key", [])
        if key == [("file_unique_id", 1)] and info.get("unique"):
            try:
                await files.drop_index(index_name)
                print(
                    f"✅ Removed legacy unique index: {index_name}",
                    flush=True
                )
            except Exception as e:
                print(
                    f"⚠️ Could not drop legacy index {index_name}: {e}",
                    flush=True
                )


async def _migrate_legacy_file_sizes(files):
    """Copy legacy file_size into file_size_bytes where necessary."""
    try:
        result = await files.update_many(
            {
                "file_size_bytes": {"$exists": False},
                "file_size": {"$exists": True}
            },
            [{"$set": {"file_size_bytes": "$file_size"}}]
        )
        if result.modified_count:
            print(
                f"✅ Migrated {result.modified_count:,} legacy file sizes",
                flush=True
            )
    except Exception as e:
        # Do not prevent the bot from starting solely because an old optional
        # field could not be migrated. The main index below is partial anyway.
        print(f"⚠️ Legacy file-size migration notice: {e}", flush=True)


async def _remove_exact_duplicate_files(files):
    """Keep one document for every exact (file_name, file_size_bytes) pair.

    Existing databases may already contain duplicates because the old schema
    only enforced file_unique_id. Before creating the new UNIQUE compound
    index, remove only the extra copies of the exact duplicate pair.

    Documents without a filename or byte size are deliberately excluded;
    they are not considered valid duplicate keys.
    """
    pipeline = [
        {
            "$match": {
                "file_name": {"$exists": True, "$nin": [None, ""]},
                "file_size_bytes": {"$exists": True, "$type": ["int", "long", "double"]}
            }
        },
        {
            "$group": {
                "_id": {
                    "file_name": "$file_name",
                    "file_size_bytes": "$file_size_bytes"
                },
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }
        },
        {"$match": {"count": {"$gt": 1}}}
    ]

    duplicate_groups = 0
    duplicate_docs = 0

    try:
        cursor = files.aggregate(
            pipeline,
            allowDiskUse=True,
            batchSize=100
        )

        async for group in cursor:
            ids = group.get("ids", [])
            if len(ids) <= 1:
                continue

            # Keep the first document and remove only the extra copies.
            extras = ids[1:]
            if extras:
                result = await files.delete_many({"_id": {"$in": extras}})
                duplicate_groups += 1
                duplicate_docs += result.deleted_count

        if duplicate_docs:
            print(
                "✅ Removed exact duplicate file records: "
                f"{duplicate_docs:,} from {duplicate_groups:,} groups",
                flush=True
            )
        else:
            print("✅ No existing exact file duplicates found", flush=True)

    except Exception as e:
        # If this migration fails, do not hide the real reason behind a later
        # index error. Re-raise so deployment shows the exact migration issue.
        print(f"❌ Exact duplicate migration failed: {e}", flush=True)
        raise


# ================= CREATE INDEXES ================= #

async def create_indexes():
    users = get_collection("users")
    files = get_collection("files")
    chats = get_collection("chats")
    searches = get_collection("searches")

    # One-time-safe migration for the existing CinemaVeta.files collection.
    await _drop_legacy_file_unique_index(files)
    await _migrate_legacy_file_sizes(files)
    await _remove_exact_duplicate_files(files)

    tasks = [
        # ---------------- USERS ---------------- #
        users.create_index("user_id", unique=True, background=True),

        # ---------------- CHATS ---------------- #
        chats.create_index("chat_id", unique=True, background=True),

        # ---------------- SEARCHES ---------------- #
        searches.create_index("search_id", unique=True, background=True),

        # ---------------- FILES ---------------- #
        # file_unique_id is intentionally NON-UNIQUE.
        files.create_index("file_unique_id", background=True),

        # The ONLY duplicate rule:
        # exact same filename + exact same byte size = duplicate.
        # Partial filter avoids null/missing legacy records colliding.
        files.create_index(
            [("file_name", 1), ("file_size_bytes", 1)],
            unique=True,
            partialFilterExpression={
                "file_name": {"$exists": True},
                "file_size_bytes": {"$exists": True}
            },
            background=True,
            name="file_name_size_unique"
        ),
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
    print("✅ Database Indexes Initialized & Synchronized", flush=True)


# ================= CLOSE DATABASE ================= #

async def close_database():
    global client

    if client:
        client.close()
        client = None


# ================= FILE HELPERS ================= #

from .models import get_file
