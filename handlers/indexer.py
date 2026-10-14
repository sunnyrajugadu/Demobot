import asyncio
import time
from pyrogram import filters
from pyrogram.errors import FloodWait, ChannelInvalid, ChannelPrivate, ChatAdminRequired
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
# FAST IDENTITY HELPER (FOR INSTANT DUPLICATE PRE-CHECK)
# ============================================================

def get_fast_file_key(message: Message):
    """Computes (renamed_file, file_size) locally in 0ms to check if already in DB"""
    media = message.document or message.video
    if not media:
        return None
    original_name = getattr(media, "file_name", None) or "Unknown"
    cleaned_name = clean_name(original_name) or original_name
    extension = ""
    if "." in original_name:
        extension = "." + original_name.rsplit(".", 1)[-1]
    renamed_file = rename_movie_file(cleaned_name, "", extension)
    file_size = getattr(media, "file_size", 0) or 0
    return (renamed_file, file_size)


# ============================================================
# CORE DATABASE SAVING LOGIC (GUARANTEED INDEXING)
# ============================================================

async def save_file_to_db(message: Message):
    """Extracts metadata and saves the exact Bot message to MongoDB"""
    media = message.document or message.video
    if not media:
        return False

    original_name = getattr(media, "file_name", None) or "Unknown"
    caption = str(getattr(message, "caption", "") or "").strip()
    cleaned_name = clean_name(original_name) or original_name
    metadata = extract_metadata(original_name, caption)

    movie_name = metadata.get("movie_name", "")
    year = metadata.get("year", "Unknown")
    languages = metadata.get("languages", [])
    quality = metadata.get("quality", "Unknown")
    audio = metadata.get("audio", "Unknown")

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

    if not movie_name:
        movie_name = cleaned_name or original_name
    if not year:
        year = "Unknown"
    if not quality:
        quality = "Unknown"
    if not audio:
        audio = "Unknown"

    movie_name = clean_movie_name(movie_name) or cleaned_name or original_name

    extension = ""
    if "." in original_name:
        extension = "." + original_name.rsplit(".", 1)[-1]

    renamed_file = rename_movie_file(cleaned_name, "", extension)

    for lang in detect_languages(renamed_file):
        if lang and lang.lower() != "unknown" and lang not in final_languages:
            if "Unknown" in final_languages:
                final_languages.remove("Unknown")
            final_languages.append(lang)

    file_size = getattr(media, "file_size", 0) or 0
    msg_date = getattr(message, "date", None)
    timestamp = int(msg_date.timestamp()) if msg_date else int(time.time())

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
    
    # Using $set ensures that even if the file exists, the new file_id updates the database
    await files().update_one(
        {
            "file_name": renamed_file,
            "file_size_bytes": file_size
        },
        {
            "$set": data
        },
        upsert=True
    )
    return True


# ============================================================
# BATCH DB SYNC HELPER (1 API CALL FOR 20 FILES + PARALLEL SAVE)
# ============================================================

async def flush_copied_batch(msg_ids: list) -> int:
    """Fetches a batch of copied messages in 1 call and saves them to MongoDB concurrently"""
    if not msg_ids:
        return 0
    try:
        bot_msgs = await app.get_messages(STORAGE_CHANNEL_ID, msg_ids)
        if not isinstance(bot_msgs, list):
            bot_msgs = [bot_msgs]
        valid_msgs = [m for m in bot_msgs if m and (m.video or m.document)]
        if not valid_msgs:
            return 0
        results = await asyncio.gather(
            *(save_file_to_db(m) for m in valid_msgs),
            return_exceptions=True
        )
        return sum(1 for r in results if r is True)
    except Exception as e:
        print(f"⚠️ Batch DB Sync Error: {e}", flush=True)
        return 0


# ============================================================
# MANUAL REINDEX COMMAND (OWNER ONLY)
# ============================================================

is_reindexing = False

@app.on_message(filters.command("reindex") & is_owner_filter)
async def manual_reindex_handler(client, message: Message):
    global is_reindexing

    if is_reindexing:
        return await message.reply_text("⚠️ <b>Reindex is already in progress. Please wait.</b>")

    is_reindexing = True
    status_msg = await message.reply_text("⚡ <b>Starting 2-Session Parallel Reindex...</b>")

    try:
        await reindex_channel(status_message=status_msg)
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Reindex Failed:</b> <code>{e}</code>")
    finally:
        is_reindexing = False


# ============================================================
# EXTERNAL CHANNEL DUMP COMMAND (FAST BATCH TURBO + DB SYNC)
# ============================================================

is_dumping = False

@app.on_message(filters.command("dump") & is_owner_filter)
async def external_dump_handler(client, message: Message):
    global is_dumping

    if is_dumping:
        return await message.reply_text("⚠️ <b>Another channel dump process is already running. Please wait until it completes.</b>")

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(
            "💡 <b>Usage Guide :</b>\n"
            "» <code>/dump &lt;channel_id_or_username&gt;</code>\n\n"
            "» <i>Public Channel :</i> <code>/dump @ChannelUsername</code>\n"
            "» <i>Private Channel :</i> <code>/dump -100xxxxxxxxxx</code>",
            quote=True
        )

    target_raw = parts[1].strip()
    try:
        target_chat = int(target_raw)
    except ValueError:
        target_chat = target_raw

    if not user_app_1:
        return await message.reply_text("❌ <b>User Session client (user_app_1) is not configured in bot.py!</b>")

    if not user_app_1.is_connected:
        try:
            await user_app_1.start()
        except Exception as conn_err:
            return await message.reply_text(f"❌ <b>Failed to start User Session:</b> <code>{conn_err}</code>")

    status_msg = await message.reply_text(f"🔍 <b>Connecting to target channel:</b> <code>{target_raw}</code>...")

    try:
        try:
            target_entity = await user_app_1.get_chat(target_chat)
        except Exception:
            # Refresh user session's dialog cache to fix "Peer id invalid" on private channels
            await status_msg.edit_text(f"🔄 <b>Refreshing session peer cache for:</b> <code>{target_raw}</code>...")
            async for dialog in user_app_1.get_dialogs():
                if dialog.chat and dialog.chat.id == target_chat:
                    break
            target_entity = await user_app_1.get_chat(target_chat)

        target_id = target_entity.id
        target_title = target_entity.title or str(target_id)
    except (ChannelInvalid, ChannelPrivate):
        return await status_msg.edit_text("❌ <b>Cannot access target channel! Make sure your user account has joined this channel.</b>")
    except Exception as err:
        return await status_msg.edit_text(f"❌ <b>Error accessing target channel:</b> <code>{err}</code>")

    is_dumping = True
    total_scanned = 0
    total_copied = 0
    total_saved = 0
    already_in_db = 0
    skipped_count = 0
    pending_batch_ids = []
    start_time = time.time()

    await status_msg.edit_text(
        f"🚀 <b>Loading existing DB cache & starting fast dump from :</b> <code>{target_title}</code>..."
    )

    # Pre-load existing (file_name, file_size_bytes) keys into memory for 0ms duplicate skipping
    existing_keys = set()
    try:
        async for doc in files().find({}, {"file_name": 1, "file_size_bytes": 1}):
            fname = doc.get("file_name")
            fsize = doc.get("file_size_bytes", 0)
            if fname:
                existing_keys.add((fname, fsize))
    except Exception as cache_err:
        print(f"⚠️ Could not preload DB cache: {cache_err}", flush=True)

    try:
        async for msg in user_app_1.get_chat_history(target_id):
            total_scanned += 1

            if not (msg.video or msg.document):
                continue

            # Instant 0ms check: if already in MongoDB, skip copying to save time & avoid FloodWait
            file_key = get_fast_file_key(msg)
            if file_key and file_key in existing_keys:
                already_in_db += 1
                continue

            copied_successfully = False
            while not copied_successfully:
                try:
                    # 1. User session copies file to storage channel
                    copied_msg = await msg.copy(chat_id=STORAGE_CHANNEL_ID)
                    pending_batch_ids.append(copied_msg.id)
                    if file_key:
                        existing_keys.add(file_key)

                    total_copied += 1
                    copied_successfully = True

                    # 2. Every 20 files, batch fetch & save to MongoDB in parallel
                    if len(pending_batch_ids) >= 20:
                        saved_now = await flush_copied_batch(pending_batch_ids)
                        total_saved += saved_now
                        pending_batch_ids.clear()

                    # Fast 0.6s pacing (3x faster than 1.5s while keeping API calls low)
                    await asyncio.sleep(0.6)

                except FloodWait as flood:
                    # Flush any pending copied files to DB before sleeping
                    if pending_batch_ids:
                        saved_now = await flush_copied_batch(pending_batch_ids)
                        total_saved += saved_now
                        pending_batch_ids.clear()

                    await status_msg.edit_text(f"⏳ <b>Telegram rate limit! Auto-pausing for {flood.value}s...</b>")
                    await asyncio.sleep(flood.value + 1)
                except Exception as copy_err:
                    print(f"⚠️ Failed to copy message ID {msg.id}: {copy_err}", flush=True)
                    skipped_count += 1
                    break

            # Update status message every 40 copied items
            if total_copied > 0 and total_copied % 40 == 0:
                elapsed = int(time.time() - start_time)
                try:
                    await status_msg.edit_text(
                        f"⚡ <b>Fast Batch Dumping & DB Syncing...</b>\n\n"
                        f"📂 <b>Target Channel :</b> <code>{target_title}</code>\n"
                        f"🔍 <b>Total Scanned :</b> <code>{total_scanned}</code>\n"
                        f"✅ <b>Newly Copied :</b> <code>{total_copied}</code>\n"
                        f"✅ <b>Saved to MongoDB :</b> <code>{total_saved}</code>\n"
                        f"⏭ <b>Already in DB (Instant Skip) :</b> <code>{already_in_db}</code>\n"
                        f"⚠️ <b>Failed :</b> <code>{skipped_count}</code>\n"
                        f"⏱ <b>Elapsed Time :</b> <code>{elapsed}s</code>"
                    )
                except Exception:
                    pass

        # Flush any remaining files in the batch at the end
        if pending_batch_ids:
            saved_now = await flush_copied_batch(pending_batch_ids)
            total_saved += saved_now
            pending_batch_ids.clear()

        elapsed_total = int(time.time() - start_time)
        await status_msg.edit_text(
            f"🎉 <b>Channel Dump & Sync Successfully Completed!</b>\n\n"
            f"📂 <b>Target Channel :</b> <code>{target_title}</code>\n"
            f"🔍 <b>Total Messages Scanned :</b> <code>{total_scanned}</code>\n"
            f"✅ <b>Newly Copied :</b> <code>{total_copied}</code>\n"
            f"✅ <b>Synced to MongoDB :</b> <code>{total_saved}</code>\n"
            f"⏭ <b>Already in DB (Skipped) :</b> <code>{already_in_db}</code>\n"
            f"⚠️ <b>Skipped / Failed :</b> <code>{skipped_count}</code>\n"
            f"⏱ <b>Total Time Taken :</b> <code>{elapsed_total}s</code>"
        )

    except Exception as dump_exc:
        if pending_batch_ids:
            saved_now = await flush_copied_batch(pending_batch_ids)
            total_saved += saved_now
            pending_batch_ids.clear()
        print(f"⚠️ Dump Execution Error: {dump_exc}", flush=True)
        await status_msg.edit_text(f"❌ <b>Dump process halted due to error:</b> <code>{dump_exc}</code>")
    finally:
        is_dumping = False


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
    """Catches any manual uploads forwarded to the storage channel and saves them."""
    try:
        # Avoid double-saving during active dump since dump flushes batches directly
        if is_dumping:
            return

        # ====================================================
        # ENSURE USER SESSION IS CONNECTED FOR REAL-TIME FETCHING
        # ====================================================
        if user_app_1 and not user_app_1.is_connected:
            await user_app_1.start()

        # Reuses the core logic function to avoid code duplication
        await save_file_to_db(message)

    except Exception as e:
        print(f"⚠️ Auto Index Error: {e}", flush=True)
