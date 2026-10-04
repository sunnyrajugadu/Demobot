import asyncio

from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from bot import app

from filters.owner import owner_filter

import database as db

from utils.logger import send_log


print(
    "✅ broadcast.py imported",
    flush=True
)


# ============================================================
# PENDING BROADCAST
# ============================================================

# Owner ID -> selected Message
pending_broadcasts = {}


# ============================================================
# BROADCAST COMMAND
# ============================================================

@app.on_message(
    filters.command("broadcast") & owner_filter,
    group=-10
)
async def broadcast_command(
    client,
    message: Message
):

    try:

        # ----------------------------------------------------
        # START BROADCAST MODE
        # ----------------------------------------------------

        pending_broadcasts[
            message.from_user.id
        ] = None

        await message.reply_text(
            "📢 Send the message to broadcast."
        )

    except Exception as e:

        print(
            f"❌ Broadcast command error: {e}",
            flush=True
        )


# ============================================================
# CAPTURE NEXT MESSAGE
# ============================================================

@app.on_message(
    owner_filter,
    group=-9
)
async def capture_broadcast_message(
    client,
    message: Message
):

    try:

        if not message.from_user:

            return

        owner_id = message.from_user.id

        # ----------------------------------------------------
        # CHECK BROADCAST MODE
        # ----------------------------------------------------

        if owner_id not in pending_broadcasts:

            return

        # ----------------------------------------------------
        # IGNORE THE /broadcast COMMAND ITSELF
        # ----------------------------------------------------

        if (
            message.text
            and message.text.startswith("/")
            and message.command
            and message.command[0].lower() == "broadcast"
        ):

            return

        # ----------------------------------------------------
        # SELECT MESSAGE
        # ----------------------------------------------------

        pending_broadcasts[
            owner_id
        ] = message

        # ----------------------------------------------------
        # CONFIRM / CANCEL
        # ----------------------------------------------------

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Confirm",
                        callback_data="broadcast_confirm"
                    ),

                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="broadcast_cancel"
                    )
                ]
            ]
        )

        await message.reply_text(
            "📢 Broadcast this message?",
            reply_markup=buttons
        )

        print(
            f"📢 Broadcast message selected by owner: "
            f"{owner_id}",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Broadcast capture error: {e}",
            flush=True
        )


# ============================================================
# CHECK BROADCAST OWNER
# ============================================================

async def check_broadcast_owner(
    query: CallbackQuery
):

    if not query.from_user:

        await query.answer(
            "❌ You're not the owner!",
            show_alert=True
        )

        return False

    if query.from_user.id not in pending_broadcasts:

        await query.answer(
            "⚠️ No pending broadcast.",
            show_alert=True
        )

        return False

    return True


# ============================================================
# CANCEL BROADCAST
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^broadcast_cancel$"
    )
)
async def broadcast_cancel(
    client,
    query: CallbackQuery
):

    try:

        # ----------------------------------------------------
        # OWNER CHECK
        # ----------------------------------------------------

        if not query.from_user:

            await query.answer(
                "❌ You're not the owner!",
                show_alert=True
            )

            return

        owner_id = query.from_user.id

        if owner_id not in pending_broadcasts:

            await query.answer(
                "⚠️ No pending broadcast.",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # REMOVE PENDING MESSAGE
        # ----------------------------------------------------

        pending_broadcasts.pop(
            owner_id,
            None
        )

        # ----------------------------------------------------
        # UPDATE CONFIRMATION MESSAGE
        # ----------------------------------------------------

        try:

            await query.message.edit_text(
                "❌ Broadcast cancelled."
            )

        except Exception as edit_error:

            print(
                f"⚠️ Broadcast cancel edit error: "
                f"{edit_error}",
                flush=True
            )

        await query.answer(
            "Broadcast cancelled."
        )

        print(
            f"❌ Broadcast cancelled by owner: "
            f"{owner_id}",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Broadcast cancel error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Cancel failed.",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# CONFIRM BROADCAST
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^broadcast_confirm$"
    )
)
async def broadcast_confirm(
    client,
    query: CallbackQuery
):

    try:

        # ----------------------------------------------------
        # OWNER CHECK
        # ----------------------------------------------------

        if not query.from_user:

            await query.answer(
                "❌ You're not the owner!",
                show_alert=True
            )

            return

        owner_id = query.from_user.id

        if owner_id not in pending_broadcasts:

            await query.answer(
                "⚠️ No pending broadcast.",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # GET SELECTED MESSAGE
        # ----------------------------------------------------

        broadcast_message = pending_broadcasts.get(
            owner_id
        )

        if not broadcast_message:

            pending_broadcasts.pop(
                owner_id,
                None
            )

            await query.answer(
                "❌ Broadcast message not found.",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # REMOVE PENDING STATE
        #
        # Prevent double-click / duplicate broadcast.
        # ----------------------------------------------------

        pending_broadcasts.pop(
            owner_id,
            None
        )

        await query.answer(
            "📢 Broadcast started..."
        )

        # ----------------------------------------------------
        # UPDATE CONFIRMATION MESSAGE
        # ----------------------------------------------------

        try:

            await query.message.edit_text(
                "📢 Broadcast started..."
            )

        except Exception as edit_error:

            print(
                f"⚠️ Broadcast status edit error: "
                f"{edit_error}",
                flush=True
            )

        # ====================================================
        # GET USERS
        # ====================================================

        users = db.get_collection(
            "users"
        )

        total = await users.count_documents(
            {}
        )

        sent = 0
        failed = 0

        # ====================================================
        # BROADCAST
        # ====================================================

        async for user in users.find({}):

            user_id = user.get(
                "user_id"
            )

            if not user_id:

                continue

            try:

                # ------------------------------------------------
                # COPY THE ORIGINAL MESSAGE
                #
                # This preserves:
                # - Text
                # - Photo
                # - Video
                # - Audio
                # - Document
                # - Animation
                # - Voice
                # - Sticker
                # - Caption
                # - Formatting
                # - Media
                # ------------------------------------------------

                await client.copy_message(
                    chat_id=int(user_id),
                    from_chat_id=(
                        broadcast_message.chat.id
                    ),
                    message_id=(
                        broadcast_message.id
                    )
                )

                sent += 1

                await asyncio.sleep(
                    0.05
                )

            except Exception as send_error:

                failed += 1

                print(
                    f"⚠️ Broadcast failed for "
                    f"{user_id}: {send_error}",
                    flush=True
                )

        # ====================================================
        # COMPLETED
        # ====================================================

        result_text = (
            "📢 <b>Broadcast Completed</b>\n\n"

            f"👥 Total: <code>{total}</code>\n"
            f"✅ Successful: <code>{sent}</code>\n"
            f"❌ Failed: <code>{failed}</code>"
        )

        try:

            await query.message.edit_text(
                result_text
            )

        except Exception as edit_error:

            print(
                f"⚠️ Broadcast result edit error: "
                f"{edit_error}",
                flush=True
            )

        # ====================================================
        # LOG
        # ====================================================

        try:

            await send_log(
                f"""
📢 <b>Broadcast Completed</b>

👤 <b>Owner:</b>
<code>{owner_id}</code>

👥 <b>Total Users:</b>
<code>{total}</code>

✅ <b>Successful:</b>
<code>{sent}</code>

❌ <b>Failed:</b>
<code>{failed}</code>

📦 <b>Message Type:</b>
<code>{get_message_type(broadcast_message)}</code>
"""
            )

        except Exception as log_error:

            print(
                f"⚠️ Broadcast Log Error: "
                f"{log_error}",
                flush=True
            )

    except Exception as e:

        print(
            f"❌ Broadcast confirm error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Broadcast failed.",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# MESSAGE TYPE
# ============================================================

def get_message_type(
    message: Message
):

    try:

        if message.text:
            return "Text"

        if message.photo:
            return "Photo"

        if message.video:
            return "Video"

        if message.audio:
            return "Audio"

        if message.document:
            return "Document"

        if message.animation:
            return "Animation"

        if message.voice:
            return "Voice"

        if message.sticker:
            return "Sticker"

        if message.video_note:
            return "Video Note"

        if message.contact:
            return "Contact"

        if message.location:
            return "Location"

        if message.venue:
            return "Venue"

        if message.poll:
            return "Poll"

        if message.dice:
            return "Dice"

        return "Other"

    except Exception:

        return "Unknown"
