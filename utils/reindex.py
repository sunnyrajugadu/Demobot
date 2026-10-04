import asyncio
import time
import zlib
from datetime import datetime
from pyrogram import raw
from pyrogram.file_id import FileId, FileUniqueId, FileType, FileUniqueType
from pyrogram.errors import FloodWait
from config import STORAGE_CHANNEL_ID
import database as db
from bot import user_app
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError
from utils.logger import send_log

print("✅ reindex.py (Full Complete Media Engine) imported", flush=True)


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
        "file_size_bytes": getattr(doc, "size", 0) or 0,
        "file_type": media_type,
        "message_id": msg_id,
        "channel_id": chat_id,
        "caption": caption or "",
        "indexed_at": timestamp,
        "updated_at": int(time.time())
    }

    return UpdateOne(
        {"file_unique_id": file_unique_id},
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
            await files_collection.bulk_write(batch, ordered=False)
        except BulkWriteError:
            pass
        except Exception:
            pass
        finally:
            queue.task_done()


# ============================================================
# COMPLETE STREAM REINDEX RUNNER
# ============================================================

async def reindex_channel(status_message=None):
    if not user_app:
        raise Exception("USER_SESSION missing. User session is required.")

    print("⚡ Starting Full Complete Reindex...", flush=True)

    await send_log(
        """
⚡ <b>Full Complete Reindex Started</b>
🚀 Scanning 100% Messages (Documents + Videos)...
"""
    )

    try:
        peer = await user_app.resolve_peer(STORAGE_CHANNEL_ID)
        chat = await user_app.get_chat(STORAGE_CHANNEL_ID)
        print(f"✅ Channel connected: {chat.title}", flush=True)
    except Exception as e:
        print(f"❌ Storage channel error: {e}", flush=True)
        raise

    files_collection = db.get_collection("files")
    queue = asyncio.Queue(maxsize=100)

    # 4 Concurrent DB writers
    NUM_WRITERS = 4
    writer_tasks = [
        asyncio.create_task(db_writer_worker(queue, files_collection))
        for _ in range(NUM_WRITERS)
    ]

    count = 0
    skipped_duplicates = 0
    batch_seen = set()
    current_batch = []
    BATCH_SIZE = 2000
    start_time = time.time()
    last_status_update = time.time()

    offset_id = 0
    LIMIT = 100

    try:
        while True:
            try:
                # Scans all channel messages sequentially (no files skipped)
                history = await user_app.invoke(
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
                print(f"⚠️ FloodWait: Sleeping {fw.value}s", flush=True)
                await asyncio.sleep(fw.value + 1)
                continue
            except Exception as req_err:
                print(f"⚠️ Network retry: {req_err}", flush=True)
                await asyncio.sleep(1)
                continue

            raw_messages = getattr(history, "messages", [])
            if not raw_messages:
                break

            offset_id = raw_messages[-1].id

            for msg in raw_messages:
                if not hasattr(msg, "media") or not msg.media:
                    continue

                media = msg.media
                doc = getattr(media, "document", None)
                is_video = False

                # Handle native Telegram videos as well
                if not doc and hasattr(media, "video"):
                    doc = getattr(media, "video", None)
                    is_video = True

                if not doc:
                    continue

                sig = zlib.crc32(f"{doc.id}:{getattr(doc, 'size', 0)}".encode("utf-8"))
                if sig in batch_seen:
                    skipped_duplicates += 1
                    continue
                batch_seen.add(sig)

                caption = getattr(msg, "message", "")
                msg_date = getattr(msg, "date", None)

                op = fast_parse_media(doc, is_video, caption, STORAGE_CHANNEL_ID, msg.id, msg_date)
                if op:
                    current_batch.append(op)
                    count += 1

                if len(current_batch) >= BATCH_SIZE:
                    await queue.put(list(current_batch))
                    current_batch.clear()

            # Dynamic live progress edit every 10 seconds
            if status_message and (time.time() - last_status_update > 10):
                elapsed = max(round(time.time() - start_time), 1)
                rate = int(count / elapsed)
                try:
                    await status_message.edit_text(
                        f"⚡ <b>Full Reindexing in progress...</b>\n\n"
                        f"📁 Total Indexed: <code>{count:,}</code>\n"
                        f"⚠️ Duplicates: <code>{skipped_duplicates:,}</code>\n"
                        f"⏱ Elapsed: <code>{elapsed}s</code>\n"
                        f"🚀 Speed: <code>~{rate:,} files/s</code>"
                    )
                    last_status_update = time.time()
                except Exception:
                    pass

            await asyncio.sleep(0)

        if current_batch:
            await queue.put(list(current_batch))
            current_batch.clear()

    finally:
        batch_seen.clear()
        for _ in range(NUM_WRITERS):
            await queue.put(None)
        await queue.join()
        await asyncio.gather(*writer_tasks)

    total_time = max(round(time.time() - start_time, 2), 0.1)
    avg_speed = int(count / total_time)

    final_text = (
        f"✅ <b>Full Complete Reindex Finished!</b> ⚡\n\n"
        f"📁 <b>Total Indexed:</b> <code>{count:,}</code>\n"
        f"⚠️ <b>Duplicates Filtered:</b> <code>{skipped_duplicates:,}</code>\n"
        f"⏱ <b>Time Taken:</b> <code>{total_time}s</code>\n"
        f"🚀 <b>Throughput:</b> <code>~{avg_speed:,} files/sec</code>"
    )

    if status_message:
        try:
            await status_message.edit_text(final_text)
        except Exception:
            pass

    await send_log(final_text)
    return count
