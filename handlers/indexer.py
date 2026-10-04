import asyncio
import time
from pyrogram import filters, errors
from pyrogram.types import Message

from bot import app
from config import STORAGE_CHANNEL_ID, OWNER_ID
from database.models import save_file
from utils.rename import (
    clean_name,
    clean_movie_name,
    rename_movie_file
)
from utils.metadata import extract_metadata
from utils.detectors import detect_languages
from utils.logger import send_log
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
# BACKGROUND BATCH LOGGER QUEUE
# ============================================================

log_queue = asyncio.Queue(maxsize=1000)
is_worker_running = False
worker_lock = asyncio.Lock()


async def log_worker():
    """Background worker to send logs sequentially without hitting Telegram rate limits."""
    global is_worker_running
    async with worker_lock:
        is_worker_running = True
        try:
            while not log_queue.empty():
                log_text = await log_queue.get()
                sent = False

                while not sent:
                    try:
                        await send_log(log_text)
                        sent = True
                        await asyncio.sleep(2.0)
                    except errors.FloodWait as fw:
                        print(f"⚠️ Telegram FloodWait in Logger: Sleeping {fw.value}s", flush=True)
                        await asyncio.sleep(fw.value)
                    except Exception as log_err:
                        print(f"⚠️ Log Worker Error: {log_err}", flush=True)
                        sent = True

                log_queue.task_done()
        finally:
            is_worker_running = False


# ============================================================
# MANUAL REINDEX COMMAND (OWNER ONLY)
# ============================================================

is_reindexing = False

@app.on_message(filters.command("reindex") & is_owner_filter)
async def manual_reindex_handler(client, message: Message):
    global is_reindexing

    if is_reindexing:
        await message.reply_text("⚠️ <b>Reindex is already running!</b> Please wait until it completes.")
        return

    is_reindexing = True
    status_msg = await message.reply_text("⚡ <b>Starting Parallel Chunk Reindex...</b>")

    try:
        total_indexed = await reindex_channel(status_message=status_msg)
        print(f"✅ Reindex finished with {total_indexed} items.", flush=True)
    except Exception as e:
        print(f"❌ Reindex failed: {e}", flush=True)
        await status_msg.edit_text(f"❌ <b>Reindex Failed:</b> <code>{e}</code>")
    finally:
        is_reindexing = False


# ============================================================
# AUTO INDEX (FOR REAL-TIME STORAGE CHANNEL UPLOADS)
# ============================================================

@app.on_message(
    filters.chat(STORAGE_CHANNEL_ID)
    & (filters.document | filters.video)
)
async def auto_index(
    client,
    message: Message
):
    global is_worker_running
    original_name = "Unknown"

    try:
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
        # SAVE TO DATABASE
        # ====================================================

        is_saved = await save_file(data)
        langs_str = ", ".join(final_languages)

        if not is_saved:
            print(f"⚠️ Skipped Duplicate: {renamed_file} (Size: {file_size} bytes)", flush=True)
            dup_log_msg = (
                f"⚠️ <b>Duplicate File Skipped</b>\n\n"
                f"📄 <b>File Name:</b> <code>{renamed_file}</code>\n"
                f"📦 <b>Size:</b> <code>{file_size} bytes</code>\n"
                f"ℹ️ <i>Same file already exists in database.</i>"
            )
            try:
                log_queue.put_nowait(dup_log_msg)
            except asyncio.QueueFull:
                pass
            return

        log_msg = (
            f"✅ <b>New File Indexed</b>\n\n"
            f"📄 <b>Original:</b> <code>{original_name}</code>\n"
            f"🎬 <b>Changed Name:</b> <code>{renamed_file}</code>\n"
            f"🗣 <b>Languages:</b> <code>{langs_str}</code>\n"
            f"📝 <b>Caption:</b> <code>{caption if caption else 'No Caption'}</code>"
        )
        try:
            log_queue.put_nowait(log_msg)
        except asyncio.QueueFull:
            pass

        print(f"✅ Indexed: {renamed_file} | Languages: {langs_str}", flush=True)

    except Exception as e:
        print(f"❌ Index Error: {e}", flush=True)
        error_log = (
            f"❌ <b>Index Failed</b>\n\n"
            f"📄 <b>File:</b> <code>{original_name}</code>\n"
            f"⚠️ <b>Error:</b> <code>{type(e).__name__}: {e}</code>"
        )
        try:
            log_queue.put_nowait(error_log)
        except asyncio.QueueFull:
            pass

    finally:
        if not is_worker_running and not log_queue.empty():
            asyncio.create_task(log_worker())
