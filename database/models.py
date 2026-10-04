import asyncio
from datetime import datetime, timezone
from pymongo import UpdateOne
import database as db
from utils.helpers import normalize_text


# ================= COLLECTIONS ================= #

def users():
    return db.get_collection("users")


def files():
    return db.get_collection("files")


def stats():
    return db.get_collection("stats")


def searches():
    return db.get_collection("searches")


def chats():
    return db.get_collection("chats")


# ================= HIGH-SPEED INDEX INITIALIZATION ================= #

async def init_db_indexes():
    """
    Establishes core performance indexes across all collections.
    """
    files_col = files()
    users_col = users()
    chats_col = chats()
    searches_col = searches()

    tasks = [
        # Files indexes
        files_col.create_index("file_unique_id", unique=True, background=True),
        files_col.create_index("movie_name", background=True),
        files_col.create_index("file_name", background=True),
        files_col.create_index([("indexed_at", -1)], background=True),
        files_col.create_index([("updated_at", -1)], background=True),
        files_col.create_index("languages", background=True),
        files_col.create_index("language", background=True),

        # Searches TTL (Auto-cleanup after 24 hours)
        searches_col.create_index("created_at", expireAfterSeconds=86400, background=True),
        searches_col.create_index("search_id", unique=True, background=True),

        # Core Entities
        users_col.create_index("user_id", unique=True, background=True),
        chats_col.create_index("chat_id", unique=True, background=True),
    ]

    try:
        await asyncio.gather(*tasks)
        print("✅ Database Indexes Initialized & Synchronized", flush=True)
    except Exception as e:
        print(f"⚠️ Index initialization notice: {e}", flush=True)


# ================= USERS ================= #

async def get_user(user_id: int):
    return await users().find_one({"user_id": user_id})


async def save_user(user_id: int, username: str = None):
    now = datetime.now(timezone.utc)

    await users().update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": username,
                "last_active": now
            },
            "$setOnInsert": {
                "join_date": now,
                "searches": 0,
                "downloads": 0
            }
        },
        upsert=True
    )


async def update_activity(user_id: int):
    await users().update_one(
        {"user_id": user_id},
        {
            "$set": {
                "last_active": datetime.now(timezone.utc)
            }
        }
    )


async def increase_search_count(user_id: int):
    await users().update_one(
        {"user_id": user_id},
        {
            "$inc": {
                "searches": 1
            }
        }
    )


async def increase_download_count(user_id: int, count: int = 1):
    await users().update_one(
        {"user_id": user_id},
        {
            "$inc": {
                "downloads": count
            }
        }
    )


# ================= CHATS ================= #

async def save_chat(chat_id: int, chat_type: str = "private", user_id: int = None):
    now = datetime.now(timezone.utc)

    # Pyrogram ChatType Enum Compatibility
    if hasattr(chat_type, "value"):
        chat_type = chat_type.value
    else:
        chat_type = str(chat_type)

    await chats().update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "chat_type": chat_type,
                "user_id": user_id,
                "last_active": now
            },
            "$setOnInsert": {
                "join_date": now
            }
        },
        upsert=True
    )


# ================= SEARCH ================= #

async def search_files(query: str, language=None, limit: int = 100):
    query = normalize_text(query)
    words = query.split()
    condition = []

    for word in words:
        condition.append(
            {
                "$or": [
                    {"movie_name": {"$regex": word, "$options": "i"}},
                    {"file_name": {"$regex": word, "$options": "i"}}
                ]
            }
        )

    mongo_query = {"$and": condition} if condition else {}

    # Language Filter
    if language and language.lower() != "all":
        language = language.strip()
        language_query = {
            "$or": [
                {"languages": {"$in": [language]}},
                {"languages": {"$elemMatch": {"$regex": f"^{language}$", "$options": "i"}}},
                {"language": {"$regex": f"^{language}$", "$options": "i"}}
            ]
        }

        if "$and" in mongo_query:
            mongo_query["$and"].append(language_query)
        else:
            mongo_query = {"$and": [language_query]}

    cursor = files().find(mongo_query).sort("_id", -1)
    if limit:
        cursor = cursor.limit(limit)

    return await cursor.to_list(length=limit)


# ================= LANGUAGES ================= #

async def get_languages(movie):
    results = await search_files(movie, limit=60)
    languages = set()

    for file in results:
        file_languages = file.get("languages", [])
        if isinstance(file_languages, str):
            file_languages = [file_languages]

        for lang in file_languages:
            if lang and str(lang).lower() != "unknown":
                languages.add(str(lang))

        old_language = file.get("language")
        if old_language and str(old_language).lower() != "unknown":
            languages.add(str(old_language))

    return sorted(languages)


async def get_language_files(movie, language):
    return await search_files(movie, language)


# ================= SINGLE FILE ================= #

async def get_file(file_id):
    from bson import ObjectId
    try:
        return await files().find_one({"_id": ObjectId(file_id)})
    except Exception:
        return await files().find_one({"file_unique_id": file_id})


# ================= DUPLICATE CHECK ================= #

async def is_file_exists(file_name: str, file_size: int = None) -> bool:
    if not file_name:
        return False

    query = {"file_name": file_name}
    if file_size is not None:
        query["$or"] = [
            {"file_size_bytes": file_size},
            {"file_size": file_size}
        ]

    doc = await files().find_one(query, {"_id": 1})
    return doc is not None


# ================= SAVE SEARCH CACHE ================= #

async def save_search_cache(search_id, files_list, movie_name=None):
    for file in files_list:
        if "_id" in file:
            file["_id"] = str(file["_id"])

    now = datetime.now(timezone.utc)

    await searches().update_one(
        {"search_id": search_id},
        {
            "$set": {
                "search_id": search_id,
                "movie_name": movie_name,
                "files": files_list,
                "current_files": files_list,
                "selected_language": "All",
                "current_page": 1,
                "created_at": now,
                "created_timestamp": now.timestamp()
            }
        },
        upsert=True
    )


async def get_search_cache(search_id):
    return await searches().find_one({"search_id": search_id})


# ================= SEARCH STATE UPDATE ================= #

async def update_search_state(search_id, current_files, language="All", page=1):
    for file in current_files:
        if "_id" in file:
            file["_id"] = str(file["_id"])

    await searches().update_one(
        {"search_id": search_id},
        {
            "$set": {
                "current_files": current_files,
                "selected_language": language,
                "current_page": page
            }
        }
    )


async def get_search_files(search_id):
    data = await get_search_cache(search_id)
    if not data:
        return []
    return data.get("files", [])


async def get_search_page(search_id, page, limit=7):
    all_files = await get_search_files(search_id)
    start = (page - 1) * limit
    end = start + limit
    return all_files[start:end]


async def get_total_pages(search_id, limit=7):
    all_files = await get_search_files(search_id)
    total = len(all_files)
    return (total + limit - 1) // limit


# ================= SAVE FILE (SINGLE & BULK) ================= #

def _prepare_file_payload(data: dict) -> dict:
    data = dict(data)
    if not data.get("movie_name"):
        data["movie_name"] = data.get("file_name", "Unknown")

    if not data.get("file_name"):
        data["file_name"] = data["movie_name"]

    if "file_size_bytes" not in data:
        data["file_size_bytes"] = data.get("file_size", 0)

    if "languages" not in data or not data["languages"]:
        if "language" in data:
            old_language = data.get("language")
            if isinstance(old_language, list):
                data["languages"] = old_language
            elif old_language:
                data["languages"] = [old_language]
            else:
                data["languages"] = ["Unknown"]
        else:
            data["languages"] = ["Unknown"]

    if isinstance(data.get("languages"), str):
        data["languages"] = [data["languages"]]

    data["languages"] = [
        str(lang).strip()
        for lang in data["languages"]
        if lang
    ]

    if not data["languages"]:
        data["languages"] = ["Unknown"]

    data["language"] = " + ".join(data["languages"]) if data["languages"] != ["Unknown"] else "Unknown"

    if "audio" not in data:
        data["audio"] = []

    if isinstance(data["audio"], str):
        if data["audio"].strip():
            data["audio"] = [data["audio"].strip()]
        else:
            data["audio"] = []

    if not data.get("quality"):
        data["quality"] = "Unknown"

    thumb_url = data.get("thumb_url") or data.get("poster_url") or None
    data["thumb_url"] = thumb_url
    data["poster_url"] = thumb_url

    return data


async def save_file(data: dict, check_duplicates: bool = True) -> bool:
    data = _prepare_file_payload(data)

    if check_duplicates:
        file_name = data.get("file_name")
        file_size = data.get("file_size_bytes")
        file_unique_id = data.get("file_unique_id")

        duplicate_query = {
            "file_name": file_name,
            "$or": [
                {"file_size_bytes": file_size},
                {"file_size": file_size}
            ]
        }

        if file_unique_id:
            duplicate_query["file_unique_id"] = {"$ne": file_unique_id}

        existing_file = await files().find_one(duplicate_query, {"_id": 1})
        if existing_file:
            return False

    await files().update_one(
        {"file_unique_id": data["file_unique_id"]},
        {"$set": data},
        upsert=True
    )
    return True


async def save_files_bulk(batch_operations: list):
    if not batch_operations:
        return
    await files().bulk_write(batch_operations, ordered=False)


# ================= STATS ================= #

async def add_stat(key: str):
    await stats().update_one(
        {"_id": "global"},
        {"$inc": {key: 1}},
        upsert=True
    )


# ================= FINAL COMPATIBILITY ================= #

async def get_languages_for_movie(movie):
    return await get_languages(movie)
