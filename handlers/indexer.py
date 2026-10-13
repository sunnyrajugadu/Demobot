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
# EXTERNAL CHANNEL DUMP COMMAND (OWNER ONLY)
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
    skipped_count = 0
    start_time = time.time()

    await status_msg.edit_text(
        f"🚀 <b>Starting full dump from :</b> <code>{target_title}</code>\n"
        f"<i>Scanning all files from the channel history...</i>"
    )

    try:
        async for msg in user_app_1.get_chat_history(target_id):
            total_scanned += 1

            if not (msg.video or msg.document):
                continue

            copied_successfully = False
            while not copied_successfully:
                try:
                    await msg.copy(chat_id=STORAGE_CHANNEL_ID)
                    total_copied += 1
                    copied_successfully = True
                    await asyncio.sleep(1.2)  # Safe delay to prevent Telegram flood limits
                except FloodWait as flood:
                    await status_msg.edit_text(f"⏳ <b>Telegram rate limit reached. Sleeping for {flood.value} seconds...</b>")
                    await asyncio.sleep(flood.value + 1)
                except Exception as copy_err:
                    print(f"⚠️ Failed to copy message ID {msg.id}: {copy_err}", flush=True)
                    skipped_count += 1
                    break

            # Update status message every 15 copied items
            if total_copied > 0 and total_copied % 15 == 0:
                elapsed = int(time.time() - start_time)
                try:
                    await status_msg.edit_text(
                        f"⚡ <b>Dumping In Progress...</b>\n\n"
                        f"📂 <b>Target Channel :</b> <code>{target_title}</code>\n"
                        f"🔍 <b>Total Messages Scanned :</b> <code>{total_scanned}</code>\n"
                        f"✅ <b>Files Copied & Indexed :</b> <code>{total_copied}</code>\n"
                        f"⚠️ <b>Skipped / Failed :</b> <code>{skipped_count}</code>\n"
                        f"⏱ <b>Elapsed Time :</b> <code>{elapsed}s</code>"
                    )
                except Exception:
                    pass

        elapsed_total = int(time.time() - start_time)
        await status_msg.edit_text(
            f"🎉 <b>Channel Dump Successfully Completed!</b>\n\n"
            f"📂 <b>Target Channel :</b> <code>{target_title}</code>\n"
            f"🔍 <b>Total Messages Scanned :</b> <code>{total_scanned}</code>\n"
            f"✅ <b>Successfully Copied & Saved :</b> <code>{total_copied}</code>\n"
            f"⚠️ <b>Skipped / Failed :</b> <code>{skipped_count}</code>\n"
            f"⏱ <b>Total Time Taken :</b> <code>{elapsed_total}s</code>"
        )

    except Exception as dump_exc:
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
