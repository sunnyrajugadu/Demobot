"""
High-reliability Telegram storage-channel reindexer.

Rules:
- Scan every message in the configured storage channel.
- Index Telegram documents and videos.
- Duplicate means EXACT same `file_name` + EXACT same `file_size_bytes`.
- Never use `file_unique_id` as the duplicate key.
- Use two user sessions in parallel, each scanning a non-overlapping message-id range.
- Use MongoDB unordered bulk writes for throughput.
- Retry FloodWait/network errors instead of silently abandoning a page.
- Do not silently swallow database errors.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

from pyrogram import raw
from pyrogram.errors import FloodWait
from pyrogram.file_id import FileId, FileUniqueId, FileType, FileUniqueType
from pymongo import UpdateOne

from bot import user_app_1, user_app_2
from config import STORAGE_CHANNEL_ID
import database as db
from utils.logger import send_log


print("✅ reindex.py (2-session lossless document/video reindexer) imported", flush=True)


# ============================================================
# TUNING
# ============================================================

HISTORY_LIMIT = 100
DB_BATCH_SIZE = 1000
QUEUE_MAX_BATCHES = 80
DB_WRITERS = 8
STATUS_INTERVAL = 5
MAX_RETRIES = 0  # 0 = retry forever. Reindex must not abandon a page.


# ============================================================
# HELPERS
# ============================================================

def _message_timestamp(msg_date) -> int:
    if isinstance(msg_date, datetime):
        return int(msg_date.timestamp())
    if isinstance(msg_date, int):
        return msg_date
    return int(time.time())


def _extract_filename(doc) -> str:
    """Return Telegram's actual filename when present."""
    for attr in getattr(doc, "attributes", []) or []:
        if isinstance(attr, raw.types.DocumentAttributeFilename):
            return attr.file_name or ""
    return ""


def _is_video_document(doc) -> bool:
    """Telegram videos are normally MessageMediaDocument + DocumentAttributeVideo."""
    for attr in getattr(doc, "attributes", []) or []:
        if isinstance(attr, raw.types.DocumentAttributeVideo):
            return True
    return False


def _clean_title(file_name: str) -> str:
    title = file_name or "Unknown"
    for ch in (".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v", "_", "[", "]", "(", ")"):
        title = title.replace(ch, " ")
    return " ".join(title.split()).strip() or file_name or "Unknown"


def _make_file_data(doc, msg, chat_id) -> Optional[dict]:
    """Build a DB document without doing any network/DB operation."""
    if not doc:
        return None

    file_name = _extract_filename(doc)
    file_size = int(getattr(doc, "size", 0) or 0)
    is_video = _is_video_document(doc)
    media_type = "video" if is_video else "document"

    # A document without a filename is still a valid Telegram file.
    # Keep the exact empty filename as the duplicate key, per the requested rule.
    try:
        file_type = FileType.VIDEO if is_video else FileType.DOCUMENT
        file_id = FileId(
            file_type=file_type,
            dc_id=doc.dc_id,
            media_id=doc.id,
            access_hash=doc.access_hash,
            file_reference=doc.file_reference,
        ).encode()

        file_unique_id = FileUniqueId(
            file_unique_type=FileUniqueType.DOCUMENT,
            media_id=doc.id,
        ).encode()
    except Exception as exc:
        print(f"⚠️ FileId build failed for message {getattr(msg, 'id', '?')}: {exc}", flush=True)
        return None

    msg_date = getattr(msg, "date", None)
    timestamp = _message_timestamp(msg_date)
    caption = getattr(msg, "message", "") or ""

    return {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "file_name": file_name,
        "movie_name": _clean_title(file_name),
        "year": "Unknown",
        "languages": ["Unknown"],
        "language": "Unknown",
        "quality": "Unknown",
        "audio": "Unknown",
        "file_size_bytes": file_size,
        "file_type": media_type,
        "message_id": msg.id,
        "channel_id": chat_id,
        "caption": caption,
        "indexed_at": timestamp,
        "updated_at": int(time.time()),
    }


def _make_operation(data: dict) -> UpdateOne:
    """Exact duplicate identity: filename + byte size, nothing else."""
    return UpdateOne(
        {
            "file_name": data["file_name"],
            "file_size_bytes": data["file_size_bytes"],
        },
        {"$setOnInsert": data},
        upsert=True,
    )


# ============================================================
# DATABASE WRITER
# ============================================================

async def db_writer_worker(queue: asyncio.Queue, files_collection, stats: dict, worker_id: int):
    while True:
        batch = await queue.get()
        try:
            if batch is None:
                return

            # Never swallow errors: a reindex that loses DB writes is not successful.
            result = await files_collection.bulk_write(batch, ordered=False)
            stats["inserted"] += int(getattr(result, "upserted_count", 0) or 0)

        except Exception as exc:
            stats["db_errors"] += 1
            print(f"❌ DB writer {worker_id} failed: {exc}", flush=True)
            # Retry the same batch until Mongo succeeds.
            while True:
                try:
                    result = await files_collection.bulk_write(batch, ordered=False)
                    stats["inserted"] += int(getattr(result, "upserted_count", 0) or 0)
                    break
                except Exception as retry_exc:
                    stats["db_retries"] += 1
                    print(f"⚠️ DB retry {worker_id}: {retry_exc}", flush=True)
                    await asyncio.sleep(1)
        finally:
            queue.task_done()


# ============================================================
# TELEGRAM HISTORY PAGE
# ============================================================

async def _get_history_page(client, peer, offset_id: int):
    retries = 0
    while True:
        try:
            return await client.invoke(
                raw.functions.messages.GetHistory(
                    peer=peer,
                    offset_id=offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=HISTORY_LIMIT,
                    max_id=0,
                    min_id=0,
                    hash=0,
                )
            )
        except FloodWait as fw:
            wait = int(getattr(fw, "value", 1) or 1) + 1
            print(f"⚠️ FloodWait: sleeping {wait}s", flush=True)
            await asyncio.sleep(wait)
        except Exception as exc:
            retries += 1
            print(f"⚠️ Telegram history error: {exc}; retry #{retries}", flush=True)
            await asyncio.sleep(min(5, max(1, retries)))


# ============================================================
# RANGE WORKER
# ============================================================

async def fetch_range_worker(
    client,
    peer,
    start_id: int,
    end_id: int,
    queue: asyncio.Queue,
    stats: dict,
    worker_name: str,
):
    """Scan [start_id, end_id] inclusively, newest -> oldest."""

    offset_id = end_id + 1
    local_seen = set()
    last_oldest = None

    while offset_id > start_id:
        history = await _get_history_page(client, peer, offset_id)
        messages = list(getattr(history, "messages", []) or [])

        if not messages:
            break

        # Telegram normally returns descending message IDs. Sort defensively so
        # a strange server response cannot make us move the cursor backwards/forwards incorrectly.
        messages.sort(key=lambda m: getattr(m, "id", 0), reverse=True)

        batch = []

        for msg in messages:
            msg_id = int(getattr(msg, "id", 0) or 0)
            if msg_id < start_id or msg_id > end_id:
                continue

            stats["scanned_messages"] += 1

            media = getattr(msg, "media", None)
            if not media:
                continue

            # Both normal documents and Telegram videos are represented by
            # MessageMediaDocument in raw MTProto. This catches BOTH.
            doc = getattr(media, "document", None)
            if doc is None:
                continue

            data = _make_file_data(doc, msg, STORAGE_CHANNEL_ID)
            if not data:
                stats["parse_errors"] += 1
                continue

            stats["media_found"] += 1

            # Exact duplicate rule, including duplicates that appear in both sessions.
            key = (data["file_name"], data["file_size_bytes"])
            if key in local_seen:
                stats["ram_duplicates"] += 1
                continue
            local_seen.add(key)

            # Shared in-memory set prevents the two parallel ranges from ever
            # submitting the same exact key twice if the ranges touch/overlap.
            async with stats["seen_lock"]:
                if key in stats["global_seen"]:
                    stats["ram_duplicates"] += 1
                    continue
                stats["global_seen"].add(key)

            batch.append(_make_operation(data))
            stats["candidates"] += 1

            if len(batch) >= DB_BATCH_SIZE:
                await queue.put(batch)
                batch = []

        if batch:
            await queue.put(batch)

        oldest_id = min(int(getattr(m, "id", 0) or 0) for m in messages)

        # Hard protection against a broken/repeated Telegram page causing an infinite loop.
        if last_oldest is not None and oldest_id >= last_oldest:
            # We still need to move one ID down if Telegram returned the same page.
            next_offset = last_oldest - 1
        else:
            next_offset = oldest_id

        last_oldest = oldest_id
        if next_offset <= start_id:
            break

        offset_id = next_offset
        await asyncio.sleep(0)

    print(
        f"✅ {worker_name} finished range {start_id:,}-{end_id:,}",
        flush=True,
    )


async def _prepare_duplicate_indexes(files_collection):
    """
    Migrate the old schema which incorrectly made file_unique_id unique.

    We deliberately do NOT make filename+size unique here because an existing
    database may already contain historical duplicates. The reindexer itself
    performs an exact-key atomic upsert and an in-memory cross-worker filter.
    """
    try:
        indexes = await files_collection.index_information()
        for name, info in indexes.items():
            key = info.get("key", [])
            unique = bool(info.get("unique", False))
            if unique and key == [("file_unique_id", 1)]:
                print(f"⚙️ Removing legacy unique index: {name}", flush=True)
                await files_collection.drop_index(name)

        # Fast lookup for the exact duplicate identity.
        await files_collection.create_index(
            [("file_name", 1), ("file_size_bytes", 1)],
            background=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Could not prepare MongoDB duplicate indexes: {exc}") from exc


# ============================================================
# MAIN REINDEX
# ============================================================

async def reindex_channel(status_message=None):
    clients = [c for c in (user_app_1, user_app_2) if c]
    if not clients:
        raise RuntimeError("At least one user session is required for reindexing.")

    print("⚡ Starting lossless Telegram reindex...", flush=True)

    # Start available sessions. If only one session exists, it still works completely.
    for client in clients:
        if not client.is_connected:
            await client.start()

    await send_log(
        "⚡ <b>Lossless Reindex Started</b>\n"
        "📁 Scanning all channel messages for documents + videos.\n"
        "🔒 Duplicate rule: exact filename + exact byte size."
    )

    # Resolve the peer separately for each session.
    peers = []
    for i, client in enumerate(clients, 1):
        try:
            peers.append(await client.resolve_peer(STORAGE_CHANNEL_ID))
        except Exception as exc:
            raise RuntimeError(f"User session {i} cannot access storage channel: {exc}") from exc

    try:
        chat = await clients[0].get_chat(STORAGE_CHANNEL_ID)
        channel_title = getattr(chat, "title", str(STORAGE_CHANNEL_ID))
    except Exception:
        channel_title = str(STORAGE_CHANNEL_ID)

    # Get the actual newest message ID. No guessed fallback: guessing can skip data.
    latest = await _get_history_page(clients[0], peers[0], 0)
    latest_messages = list(getattr(latest, "messages", []) or [])
    if not latest_messages:
        if status_message:
            await status_message.edit_text("⚠️ <b>Storage channel is empty.</b>")
        return 0

    max_msg_id = max(int(getattr(m, "id", 0) or 0) for m in latest_messages)
    min_msg_id = 1

    files_collection = db.get_collection("files")
    await _prepare_duplicate_indexes(files_collection)
    queue = asyncio.Queue(maxsize=QUEUE_MAX_BATCHES)

    stats = {
        "scanned_messages": 0,
        "media_found": 0,
        "candidates": 0,
        "inserted": 0,
        "ram_duplicates": 0,
        "parse_errors": 0,
        "db_errors": 0,
        "db_retries": 0,
        "global_seen": set(),
        "seen_lock": asyncio.Lock(),
    }

    writer_tasks = [
        asyncio.create_task(db_writer_worker(queue, files_collection, stats, i + 1))
        for i in range(DB_WRITERS)
    ]

    start_time = time.time()

    # Split only by message ID. Every ID belongs to exactly one worker.
    if len(clients) == 2 and max_msg_id > 1:
        mid = (min_msg_id + max_msg_id) // 2
        ranges = [
            (mid + 1, max_msg_id),
            (min_msg_id, mid),
        ]
    else:
        ranges = [(min_msg_id, max_msg_id)]

    workers = []
    for i, (lo, hi) in enumerate(ranges):
        workers.append(
            asyncio.create_task(
                fetch_range_worker(
                    clients[i],
                    peers[i],
                    lo,
                    hi,
                    queue,
                    stats,
                    f"Session-{i + 1}",
                )
            )
        )

    async def progress_updater():
        while any(not task.done() for task in workers):
            if status_message:
                elapsed = max(time.time() - start_time, 0.1)
                speed = int(stats["media_found"] / elapsed)
                text = (
                    f"⚡ <b>Reindexing...</b>\n\n"
                    f"📦 Channel: <code>{channel_title}</code>\n"
                    f"📨 Messages scanned: <code>{stats['scanned_messages']:,}</code>\n"
                    f"📁 Media found: <code>{stats['media_found']:,}</code>\n"
                    f"💾 New records: <code>{stats['inserted']:,}</code>\n"
                    f"♻️ Exact duplicates: <code>{stats['ram_duplicates']:,}</code>\n"
                    f"🚀 Scan speed: <code>~{speed:,}/sec</code>"
                )
                try:
                    await status_message.edit_text(text)
                except Exception:
                    pass
            await asyncio.sleep(STATUS_INTERVAL)

    progress_task = asyncio.create_task(progress_updater())

    try:
        # If a worker crashes, let the error reach the caller instead of claiming success.
        await asyncio.gather(*workers)

        # Wait until every queued Mongo batch is actually written.
        await queue.join()

    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        for _ in writer_tasks:
            await queue.put(None)
        await asyncio.gather(*writer_tasks, return_exceptions=False)

    elapsed = max(time.time() - start_time, 0.1)
    speed = int(stats["media_found"] / elapsed)

    final_text = (
        "✅ <b>Lossless Reindex Finished</b> ⚡\n\n"
        f"📨 <b>Messages scanned:</b> <code>{stats['scanned_messages']:,}</code>\n"
        f"📁 <b>Documents + videos found:</b> <code>{stats['media_found']:,}</code>\n"
        f"💾 <b>New records inserted:</b> <code>{stats['inserted']:,}</code>\n"
        f"♻️ <b>Exact duplicates skipped:</b> <code>{stats['ram_duplicates']:,}</code>\n"
        f"⚠️ <b>Parse errors:</b> <code>{stats['parse_errors']:,}</code>\n"
        f"⏱ <b>Time:</b> <code>{elapsed:.1f}s</code>\n"
        f"🚀 <b>Scan speed:</b> <code>~{speed:,} media/sec</code>"
    )

    if status_message:
        try:
            await status_message.edit_text(final_text)
        except Exception:
            pass

    await send_log(final_text)
    return stats["inserted"]
