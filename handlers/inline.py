import html
import asyncio
import re
import time
from pyrogram import filters
from pyrogram.types import (
    InlineQuery,
    InlineQueryResultCachedDocument,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from bot import app
from database.models import files
from handlers.callbacks import (
    make_single_delete_message,
    make_single_instruction_message,
    delete_instruction_later,
    delete_single_file_later
)
from utils.rename import clean_file_name
from utils.caption import make_file_caption
from config import STORAGE_CHANNEL_ID
from filters.fsub import is_subscribed


print("✅ inline.py imported", flush=True)

# In-memory verified bot media cache
BOT_FILE_CACHE = {}


# ================= PARSE CHANNEL ID ================= #

def clean_channel_id(chan):
    if not chan:
        chan = STORAGE_CHANNEL_ID
    if isinstance(chan, int):
        return chan
    chan_str = str(chan).strip()
    if chan_str.startswith("-100") or (chan_str.startswith("-") and chan_str[1:].isdigit()) or chan_str.isdigit():
        try:
            return int(chan_str)
        except Exception:
            return chan_str
    return chan_str


# ================= SIZE FORMAT ================= #

def format_size(size):
    try:
        size = int(size or 0)
    except Exception:
        size = 0

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"
    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.2f} KB"
    return f"{size:.0f} B"


# ================= DISPLAY NAME ================= #

def get_file_display_name(file):
    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or "Movie"
    )
    cleaned = clean_file_name(str(raw_name))
    return cleaned if (cleaned and cleaned.lower() != "unknown") else "Movie"


# ================= BATCH VERIFY BOT FILE IDS ================= #

async def batch_resolve_bot_files(file_list):
    """Fetches real Bot-accessible file_ids strictly using bot client to eliminate DOCUMENT_INVALID"""
    channel_groups = {}

    for f in file_list:
        unique_key = f.get("file_unique_id") or str(f.get("_id"))
        if unique_key not in BOT_FILE_CACHE:
            msg_id = f.get("message_id")
            chan = clean_channel_id(f.get("channel_id") or STORAGE_CHANNEL_ID)
            if msg_id and chan:
                try:
                    m_id = int(msg_id)
                    if chan not in channel_groups:
                        channel_groups[chan] = []
                    channel_groups[chan].append((m_id, unique_key))
                except Exception:
                    pass

    for chan, items in channel_groups.items():
        msg_ids = [item[0] for item in items]
        id_to_key = {item[0]: item[1] for item in items}
        try:
            messages = await app.get_messages(chan, msg_ids)
            if not isinstance(messages, list):
                messages = [messages]

            for msg in messages:
                if not msg:
                    continue
                key = id_to_key.get(msg.id)
                if not key:
                    continue

                media = msg.document or msg.video or msg.audio
                if media:
                    media_type = "video" if msg.video else ("audio" if msg.audio else "document")
                    BOT_FILE_CACHE[key] = (media.file_id, media_type)
        except Exception as err:
            print(f"⚠️ Batch resolution note for channel {chan}: {err}", flush=True)


# ================= INLINE QUERY HANDLER ================= #

@app.on_inline_query()
async def inline_search_handler(client, query: InlineQuery):
    try:
        user = query.from_user
        if not user:
            return

        # ================= STRICT FSUB ENFORCEMENT (LINKED TO filters/fsub.py) ================= #
        if not await is_subscribed(client, user.id):
            # Passes parameter 'inline_fsub' to directly trigger FSub flow inside /start
            return await query.answer(
                results=[],
                switch_pm_text="You must join our channels before using this feature",
                switch_pm_parameter="inline_fsub",
                cache_time=0,
                is_personal=True
            )

        raw_query = query.query or ""
        search_text = raw_query.strip()
        offset = int(query.offset or 0)
        limit = 30
        results = []

        # 1. Fast Single-Pass Database Query with Latest Indexed Priority
        if not search_text:
            cursor = files().find().sort([("indexed_at", -1), ("_id", -1)]).skip(offset).limit(limit)
            file_list = await cursor.to_list(length=limit)
            try:
                display_count = await files().estimated_document_count()
            except Exception:
                display_count = len(file_list)
            pm_tag = "start"
        else:
            words = [re.escape(w) for w in search_text.split() if w]
            if words:
                search_filter = {
                    "$and": [
                        {
                            "$or": [
                                {"file_name": {"$regex": w, "$options": "i"}},
                                {"original_file_name": {"$regex": w, "$options": "i"}},
                                {"movie_name": {"$regex": w, "$options": "i"}}
                            ]
                        } for w in words
                    ]
                }
            else:
                search_filter = {}

            pipeline = [
                {"$match": search_filter},
                {"$sort": {"indexed_at": -1, "_id": -1}},
                {
                    "$facet": {
                        "total": [{"$count": "count"}],
                        "data": [{"$skip": offset}, {"$limit": limit}]
                    }
                }
            ]

            facet_res = await files().aggregate(pipeline).to_list(length=1)
            
            if facet_res and len(facet_res) > 0:
                total_arr = facet_res[0].get("total", [])
                display_count = total_arr[0]["count"] if total_arr else 0
                file_list = facet_res[0].get("data", [])
            else:
                display_count = 0
                file_list = []

            pm_tag = f"q_{abs(hash(search_text)) % 100000}"

        # 2. Instant Zero Results Handler
        if display_count == 0 and offset == 0:
            return await query.answer(
                results=[],
                switch_pm_text="📁 Results - 0",
                switch_pm_parameter="none",
                cache_time=0,
                is_personal=True
            )

        # Batch resolve storage channel file IDs
        await batch_resolve_bot_files(file_list)

        # 3. Direct Native Media Cards (100% Verified Bot IDs Only)
        for index, f in enumerate(file_list, start=offset + 1):
            file_id = str(f.get("_id"))
            unique_key = f.get("file_unique_id") or file_id
            display_name = get_file_display_name(f)
            caption = make_file_caption(f)

            cached_item = BOT_FILE_CACHE.get(unique_key)
            if cached_item:
                file_ref, actual_type = cached_item
            else:
                continue

            file_size = format_size(f.get("file_size_bytes", 0))
            description_text = f"Size: {file_size}\nType: {actual_type.capitalize()}"

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Search Again", switch_inline_query_current_chat="")]
            ])

            try:
                results.append(
                    InlineQueryResultCachedDocument(
                        id=f"doc_{file_id}_{index}",
                        document_file_id=file_ref,
                        title=display_name,
                        description=description_text,
                        caption=caption,
                        reply_markup=markup
                    )
                )
            except Exception:
                continue

        next_offset = str(offset + limit) if (offset + limit) < display_count else ""

        # Instant Live Header Update on First Search Hit
        await query.answer(
            results=results,
            switch_pm_text=f"📁 Results - {display_count}",
            switch_pm_parameter=pm_tag,
            next_offset=next_offset,
            cache_time=0,
            is_personal=True
        )

    except Exception as e:
        print(f"❌ INLINE ERROR: {e}", flush=True)
        try:
            await query.answer(results=[], cache_time=0, is_personal=True)
        except Exception:
            pass


# ================= AUTO DELETE & SEND INSTRUCTION / NOTIFICATION MESSAGE ================= #

@app.on_message(filters.via_bot & (filters.document | filters.video | filters.audio | filters.animation | filters.photo))
async def auto_delete_inline_file(client, message):
    try:
        chat_id = message.chat.id
        user = message.from_user

        # 1. Send separate instruction message that deletes in 30 seconds
        try:
            instruction_msg = await client.send_message(
                chat_id=chat_id,
                text=make_single_instruction_message()
            )
            if instruction_msg:
                asyncio.create_task(
                    delete_instruction_later(
                        client=client,
                        chat_id=chat_id,
                        message_id=instruction_msg.id
                    )
                )
        except Exception as ins_err:
            print(f"⚠️ Inline instruction message error: {ins_err}", flush=True)

        # 2. Trigger standard 5 minutes auto-delete for the sent file
        if user:
            asyncio.create_task(
                delete_single_file_later(
                    client=client,
                    chat_id=chat_id,
                    message_id=message.id,
                    user=user
                )
            )
        else:
            # Fallback if user object is missing
            asyncio.sleep(300)
            await message.delete()
            delete_text = (
                "⚠️ <b>Your Request Has Been Deleted 👍🏻</b>\n"
                "(Due To Avoid Copyright Issues 😌)\n\n"
                "<b>If You Want That File, Request Again ❤️</b>"
            )
            deleted_notice = await client.send_message(
                chat_id=chat_id,
                text=delete_text
            )
            await asyncio.sleep(30)
            await deleted_notice.delete()

    except Exception as e:
        print(f"⚠️ Inline Auto-delete error: {e}", flush=True)
