import asyncio
import time
from pyrogram import filters
from pyrogram.types import Message

from bot import app, user_app_1
from config import STORAGE_CHANNEL_ID, OWNER_ID
from database.models import files
from utils.rename import (
    clean_name,
    clean_movie_name,
    rename_movie_file
)
from utils.metadata import extract_metadata
from utils.detectors import detect_languages
from utils.reindex import reindex_channel

print("✅ indexer.py imported", flush=True)

# ============================================================
# OWNER FILTER
# ============================================================

def owner_check(_, __, message: Message):
    if not message.from_user:
        return False
    if isinstance(OWNER_ID, list):
        return message.from_user.id in OWNER_ID
    return message.from_user.id == OWNER_ID

is_owner_filter = filters.create(owner_check)


# ============================================================
# MANUAL REINDEX COMMAND (OWNER ONLY)
# ============================================================

is_reindexing = False

@app.on_message(filters.command("reindex") & is_owner_filter)
async def manual_reindex_handler(client, message: Message):
    global is_reindexing

    if is_reindexing:
        return

    is_reindexing = True
    status_msg = await message.reply_text("⚡ <b>Starting 2-Session Parallel Reindex...</b>")

    try:
        await reindex_channel(status_message=status_msg)
    except Exception:
        pass
    finally:
        is_reindexing = False


# ============================================================
# AUTO INDEX (SILENT REAL-TIME STORAGE CHANNEL UPLOADS)
# ============================================================

@app.on_message(
    filters.chat(STORAGE_CHANNEL_ID)
    & (filters.document | filters.video)
)
async def auto_index(
    client,
    message: Message
):
    try:
        # ====================================================
        # ENSURE USER SESSION IS CONNECTED FOR REAL-TIME FETCHING
        # ====================================================
        if user_app_1 and not user_app_1.is_connected:
            await user_app_1.start()

        # ====================================================
        # GET MEDIA
        # ====================================================

        media = message.document or message.video
        if not media:
            return

        # ====================================================
        # ORIGINAL FILE NAME
        # ====================================================

        original_name = getattr(media, "file_name", None) or "Unknown"

        # ====================================================
        # CAPTION
        # ====================================================

        caption = str(getattr(message, "caption", "") or "").strip()

        # ====================================================
        # CLEAN ORIGINAL NAME
        # ====================================================

        cleaned_name = clean_name(original_name) or original_name

        # ====================================================
        # EXTRACT ALL METADATA
        # ====================================================

        metadata = extract_metadata(original_name, caption)

        movie_name = metadata.get("movie_name", "")
        year = metadata.get("year", "Unknown")
        languages = metadata.get("languages", [])
        quality = metadata.get("quality", "Unknown")
        audio = metadata.get("audio", "Unknown")

        # ====================================================
        # ADVANCED MULTI-LANGUAGE RESOLVER
        # ====================================================

        detected_set = set()

        if isinstance(languages, list):
            for l in languages:
                if l and str(l).lower() != "unknown":
                    detected_set.add(str(l).strip())
        elif isinstance(languages, str) and languages.lower() != "unknown":
            for l in languages.split("+"):
                if l.strip():
                    detected_set.add(l.strip())

        for text_source in (original_name, caption):
            if text_source:
                for lang in detect_languages(text_source):
                    if lang and lang.lower() != "unknown":
                        detected_set.add(lang)

        final_languages = list(detected_set) if detected_set else ["Unknown"]

        # ====================================================
        # SAFETY NORMALIZATION
        # ====================================================

        if not movie_name:
            movie_name = cleaned_name or original_name

        if not year:
            year = "Unknown"

        if not quality:
            quality = "Unknown"

        if not audio:
            audio = "Unknown"

        # ====================================================
        # FINAL MOVIE NAME CLEAN
        # ====================================================

        movie_name = clean_movie_name(movie_name) or cleaned_name or original_name

        # ====================================================
        # FILE EXTENSION
        # ====================================================

        extension = ""
        if "." in original_name:
            extension = "." + original_name.rsplit(".", 1)[-1]

        # ====================================================
        # FINAL RENAMED FILE
        # ====================================================

        renamed_file = rename_movie_file(cleaned_name, "", extension)

        for lang in detect_languages(renamed_file):
            if lang and lang.lower() != "unknown" and lang not in final_languages:
                if "Unknown" in final_languages:
                    final_languages.remove("Unknown")
                final_languages.append(lang)

        # ====================================================
        # FILE SIZE & TIMESTAMPS
        # ====================================================

        file_size = getattr(media, "file_size", 0) or 0
        msg_date = getattr(message, "date", None)
        timestamp = int(msg_date.timestamp()) if msg_date else int(time.time())

        # ====================================================
        # FILE DATA
        # ====================================================

        data = {
            "file_id": media.file_id,
            "file_unique_id": media.file_unique_id,
            "file_name": renamed_file,
            "movie_name": movie_name,
            "year": year,
            "languages": final_languages,
            "language": " + ".join(final_languages) if final_languages != ["Unknown"] else "Unknown",
            "quality": quality,
            "audio": audio,
            "original_file_name": original_name,
            "caption": caption,
            "file_size_bytes": file_size,
            "file_type": "video" if message.video else "document",
            "message_id": message.id,
            "channel_id": message.chat.id,
            "indexed_at": timestamp,
            "updated_at": int(time.time())
        }

        # ====================================================
        # ATOMIC DUPLICATE CHECK & SAVE (Like reindex.py)
        # ====================================================
        
        await files().update_one(
            {
                "file_name": renamed_file,
                "file_size_bytes": file_size
            },
            {
                "$setOnInsert": data
            },
            upsert=True
        )

    except Exception as e:
        print(f"⚠️ Auto Index Error: {e}", flush=True)
