import asyncio
import time
from datetime import datetime
from pyrogram import raw
from pyrogram.file_id import FileId, FileUniqueId, FileType, FileUniqueType
from pyrogram.errors import FloodWait
from config import STORAGE_CHANNEL_ID
import database as db
from bot import user_app_1, user_app_2
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError
from utils.logger import send_log

print("✅ reindex.py (Ultra-Optimized 2-User Sessions Parallel Engine) imported", flush=True)


# ============================================================
# FAST IN-MEMORY MEDIA PARSER (DOCUMENTS + VIDEOS)
# ============================================================

def fast_parse_media(doc, is_video, caption, chat_id, msg_id, msg_date):
    file_name = ""
    media_type = "video" if is_video else "document"

    for attr in getattr(doc, "attributes", []):
        if isinstance(attr, raw.types.DocumentAttributeFilename):
            file_name = attr.file_name
        elif isinstance(attr, raw.types.DocumentAttributeVideo):
            media_type = "video"

    f_type = FileType.VIDEO if media_type == "video" else FileType.DOCUMENT
    u_type = FileUniqueType.DOCUMENT

    file_id = FileId(
        file_type=f_type,
        dc_id=doc.dc_id,
        media_id=doc.id,
        access_hash=doc.access_hash,
        file_reference=doc.file_reference
    ).encode()

    file_unique_id = FileUniqueId(
        file_unique_type=u_type,
        media_id=doc.id
    ).encode()

    clean_title = file_name
    for ch in (".mkv", ".mp4", ".avi", ".webm", "_", "[", "]", "(", ")"):
        clean_title = clean_title.replace(ch, " ")
    clean_title = " ".join(clean_title.split()).strip() or file_name

    if isinstance(msg_date, int):
        timestamp = msg_date
    elif isinstance(msg_date, datetime):
        timestamp = int(msg_date.timestamp())
    else:
        timestamp = int(time.time())

    file_size = getattr(doc, "size", 0) or 0

    data = {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "file_name": file_name,
        "movie_name": clean_title,
        "year": "Unknown",
        "languages": ["Unknown"],
        "language": "Unknown",
        "quality": "Unknown",
        "audio": "Unknown",
        "file_size_bytes": file_size,
        "file_type": media_type,
        "message_id": msg_id,
        "channel_id": chat_id,
        "caption": caption or "",
        "indexed_at": timestamp,
        "updated_at": int(time.time())
    }

    # ============================================================
    # 🔴 DB DUPLICATE CHECK FIX (Name + Size Exact Match)
    # Using MongoDB's blazingly fast atomic upsert with the compound index.
    # It will only insert if BOTH file_name and file_size_bytes don't exist together.
    # ============================================================
    return UpdateOne(
        {
            "file_name": file_name,
            "file_size_bytes": file_size
        },
        {"$setOnInsert": data},
        upsert=True
    )


# ============================================================
# ASYNC MONGO BULK INGESTION WORKER
# ============================================================

async def db_writer_worker(queue, files_collection):
    while True:
        batch = await queue.get()
        if batch is None:
            queue.task_done()
            break
        try:
            # unordered=False allows MongoDB to process the batch concurrently.
            await files_collection.bulk_write(batch, ordered=False)
        except BulkWriteError:
            # BulkWriteError will catch duplicate key errors if any slip through,
            # ignoring them and letting valid ones pass.
            pass
        except Exception:
            pass
        finally:
            queue.task_done()


# ============================================================
# WORKER FOR FETCHING A SPECIFIC MESSAGE ID RANGE (PER CLIENT)
# ============================================================

async def fetch_range_worker(client, peer, start_id, end_id, queue, stats):
    offset_id = end_id  # Start from newer message and go backwards towards start_id
    LIMIT = 500  # Batch retrieval limit

    while offset_id >= start_id:
        try:
            history = await client.invoke(
                raw.functions.messages.GetHistory(
                    peer=peer,
                    offset_id=offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=LIMIT,
                    max_id=0,
                    min_id=0,
                    hash=0
                )
            )
        except FloodWait as fw:
            print(f"⚠️ FloodWait on client: Sleeping {fw.value}s", flush=True)
            await asyncio.sleep(fw.value + 1)
            continue
        except Exception as req_err:
            print(f"⚠️ Network retry error: {req_err}", flush=True)
            await asyncio.sleep(1)
            continue

        raw_messages = getattr(history, "messages", [])
        if not raw_messages:
            break

        current_batch = []
        for msg in raw_messages:
            if msg.id < start_id:
                continue

            if not hasattr(msg, "media") or not msg.media:
                continue

            media = msg.media
            doc = getattr(media, "document", None)
            is_video = False

            if not doc and hasattr(media, "video"):
                doc = getattr(media, "video", None)
                is_video = True

            if not doc:
                continue

            # ============================================================
            # 🔴 IN-MEMORY DUPLICATE CHECK (Name + Size Exact Match)
            # Extremely fast RAM check. Removes the slow DB find_one bottleneck.
            # ============================================================
            temp_file_name = ""
            for attr in getattr(doc, "attributes", []):
                if isinstance(attr, raw.types.DocumentAttributeFilename):
                    temp_file_name = attr.file_name
            
            temp_file_size = getattr(doc, 'size', 0) or 0
            
            exact_match_key = f"{temp_file_name}::{temp_file_size}"
            
            if exact_match_key in stats["batch_seen"]:
                stats["skipped_duplicates"] += 1
                continue
            
            stats["batch_seen"].add(exact_match_key)

            caption = getattr(msg, "message", "")
            msg_date = getattr(msg, "date", None)

            op = fast_parse_media(doc, is_video, caption, STORAGE_CHANNEL_ID, msg.id, msg_date)
            if op:
                current_batch.append(op)
                stats["count"] += 1

            if len(current_batch) >= 3000:  # Kept at 3000 for maximum throughput speed
                await queue.put(list(current_batch))
                current_batch.clear()

        if current_batch:
            await queue.put(list(current_batch))
            current_batch.clear()

        # Update offset to the oldest message received in this batch
        oldest_msg_id = raw_messages[-1].id
        if oldest_msg_id <= start_id:
            break
        offset_id = oldest_msg_id

        await asyncio.sleep(0)


# ============================================================
# COMPLETE ULTRA-FAST 2-SESSION PARALLEL STREAM REINDEX RUNNER
# ============================================================

async def reindex_channel(status_message=None):
    if not user_app_1 or not user_app_2:
        raise Exception("Both USER_SESSION_1 and USER_SESSION_2 are required for parallel reindexing.")

    print("⚡ Starting Ultra-Optimized 2-Session Parallel Reindex...", flush=True)

    # Ensure both user session clients are started
    if not user_app_1.is_connected:
        await user_app_1.start()
    if not user_app_2.is_connected:
        await user_app_2.start()

    await send_log(
        """
⚡ <b>Ultra-Optimized 2-Session Parallel Reindex Started</b>
🚀 Scanning Channel using 2 User Accounts simultaneously at max speed...
"""
    )

    try:
        # Resolve peers independently for both clients to avoid CHANNEL_INVALID errors
        peer_1 = await user_app_1.resolve_peer(STORAGE_CHANNEL_ID)
        peer_2 = await user_app_2.resolve_peer(STORAGE_CHANNEL_ID)
        chat = await user_app_1.get_chat(STORAGE_CHANNEL_ID)
        print(f"✅ Channel connected: {chat.title}", flush=True)
    except Exception as e:
        print(f"❌ Storage channel error: {e}", flush=True)
        raise

    # Fetch latest message ID to determine channel range using user_app_1 and peer_1
    try:
        latest_history = await user_app_1.invoke(
            raw.functions.messages.GetHistory(
                peer=peer_1,
                offset_id=0,
                offset_date=0,
                add_offset=0,
                limit=1,
                max_id=0,
                min_id=0,
                hash=0
            )
        )
        latest_msgs = getattr(latest_history, "messages", [])
        if not latest_msgs:
            if status_message:
                await status_message.edit_text("⚠️ Channel is empty!")
            return 0
        max_msg_id = latest_msgs[0].id
    except Exception as e:
        print(f"❌ Failed to fetch latest message ID: {e}", flush=True)
        max_msg_id = 2000000  # Fallback assumption

    min_msg_id = 1
    mid_msg_id = max_msg_id // 2

    files_collection = db.get_collection("files")
    queue = asyncio.Queue(maxsize=300)

    # 10 Concurrent DB writers for ultimate Mongo bulk ingest performance
    NUM_WRITERS = 10
    writer_tasks = [
        asyncio.create_task(db_writer_worker(queue, files_collection))
        for _ in range(NUM_WRITERS)
    ]

    stats = {
        "count": 0,
        "skipped_duplicates": 0,
        "batch_seen": set()
    }

    start_time = time.time()
    last_status_update = time.time()

    # Split work between user_app_1 and user_app_2 using their respective resolved peers
    worker_1 = asyncio.create_task(
        fetch_range_worker(user_app_1, peer_1, mid_msg_id, max_msg_id, queue, stats)
    )
    worker_2 = asyncio.create_task(
        fetch_range_worker(user_app_2, peer_2, min_msg_id, mid_msg_id - 1, queue, stats)
    )

    # Background task to live-update status message every 5 seconds
    async def progress_updater():
        nonlocal last_status_update
        while not (worker_1.done() and worker_2.done()):
            if status_message and (time.time() - last_status_update > 5):
                elapsed = max(round(time.time() - start_time), 1)
                rate = int(stats["count"] / elapsed) if elapsed > 0 else 0
                try:
                    await status_message.edit_text(
                        f"⚡ <b>Ultra-Optimized 2-Session Reindex running...</b>\n\n"
                        f"📁 Total Indexed: <code>{stats['count']:,}</code>\n"
                        f"⚠️ RAM Duplicates Skipped: <code>{stats['skipped_duplicates']:,}</code>\n"
                        f"⏱ Elapsed: <code>{elapsed}s</code>\n"
                        f"🚀 Speed: <code>~{rate:,} files/s</code>"
                    )
                    last_status_update = time.time()
                except Exception:
                    pass
            await asyncio.sleep(2)

    progress_task = asyncio.create_task(progress_updater())

    # Wait for both workers to finish fetching
    await asyncio.gather(worker_1, worker_2)
    progress_task.cancel()

    # Signal database writers to finish remaining queue items
    for _ in range(NUM_WRITERS):
        await queue.put(None)
    await queue.join()
    await asyncio.gather(*writer_tasks)

    total_time = max(round(time.time() - start_time, 2), 0.1)
    avg_speed = int(stats["count"] / total_time)

    final_text = (
        f"✅ <b>Ultra-Optimized 2-Session Reindex Finished!</b> ⚡\n\n"
        f"📁 <b>Total Indexed:</b> <code>{stats['count']:,}</code>\n"
        f"⚠️ <b>RAM Duplicates Filtered:</b> <code>{stats['skipped_duplicates']:,}</code>\n"
        f"⏱ <b>Time Taken:</b> <code>{total_time}s</code>\n"
        f"🚀 <b>Throughput:</b> <code>~{avg_speed:,} files/sec</code>"
    )

    if status_message:
        try:
            await status_message.edit_text(final_text)
        except Exception:
            pass

    await send_log(final_text)
    return stats["count"]
