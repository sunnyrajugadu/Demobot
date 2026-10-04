import importlib

from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from bot import app

from config import OWNER_ID

from filters.owner import owner_filter

from utils.reindex import reindex_channel
from utils.logger import send_log

from handlers.delete import collection_menu
from handlers.broadcast import pending_broadcasts


print(
    "✅ owner_menu.py imported",
    flush=True
)


# ============================================================
# OWNER MENU KEYBOARD
# ============================================================

def owner_menu_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "♻️ Reindex",
                    callback_data="owner_reindex"
                ),

                InlineKeyboardButton(
                    "🟡 Reload",
                    callback_data="owner_reload"
                )
            ],

            [
                InlineKeyboardButton(
                    "📢 Broadcast",
                    callback_data="owner_broadcast"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔰 Database",
                    callback_data="owner_database"
                )
            ]
        ]
    )


# ============================================================
# DATABASE MENU KEYBOARD
# ============================================================

async def database_menu_keyboard():

    keyboard = await collection_menu()

    if keyboard is None:

        rows = []

    else:

        rows = list(
            keyboard.inline_keyboard
        )

    # --------------------------------------------------------
    # ALWAYS ADD BACK TO OWNER MENU
    # --------------------------------------------------------

    rows.append(
        [
            InlineKeyboardButton(
                "⬅️ Back to Owner Menu",
                callback_data="owner_menu_back"
            )
        ]
    )

    return InlineKeyboardMarkup(
        rows
    )


# ============================================================
# OWNER MENU TEXT
# ============================================================

def owner_menu_text():

    return """
👑 **Owner Commands**

━━━━━━━━━━━━━━━━━━━━━━━━

Select a command:
"""


# ============================================================
# DATABASE MENU TEXT
# ============================================================

def database_menu_text():

    return """
🔰 **Database Manager**

━━━━━━━━━━━━━━━━━━━━━━━━

Select a collection:
"""


# ============================================================
# OWNER COMMAND
# ============================================================

@app.on_message(
    filters.command("owner") & owner_filter
)
async def owner_menu_command(
    client,
    message: Message
):

    try:

        await message.reply_text(
            owner_menu_text(),
            reply_markup=owner_menu_keyboard()
        )

    except Exception as e:

        print(
            f"❌ Owner Menu Error: {e}",
            flush=True
        )


# ============================================================
# CALLBACK OWNER CHECK
# ============================================================

async def check_callback_owner(
    query: CallbackQuery
):

    if not query.from_user:

        await query.answer(
            "❌ You're not the owner!",
            show_alert=True
        )

        return False

    if query.from_user.id != OWNER_ID:

        await query.answer(
            "❌ You're not the owner!",
            show_alert=True
        )

        return False

    return True


# ============================================================
# DATABASE BUTTON
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^owner_database$"
    )
)
async def owner_database_button(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # CALLBACK ANSWER
        # ====================================================

        await query.answer(
            "🗄 Opening database..."
        )

        # ====================================================
        # DATABASE KEYBOARD
        # ====================================================

        keyboard = await database_menu_keyboard()

        # ====================================================
        # SHOW DATABASE MENU
        # ====================================================

        await query.message.edit_text(
            database_menu_text(),
            reply_markup=keyboard
        )

    except Exception as e:

        print(
            f"❌ Database Menu Error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Database menu failed.",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# DATABASE BACK TO OWNER MENU
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^owner_menu_back$"
    )
)
async def owner_menu_back(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # CALLBACK ANSWER
        # ====================================================

        await query.answer(
            "⬅️ Owner menu"
        )

        # ====================================================
        # RESTORE OWNER MENU
        # ====================================================

        await query.message.edit_text(
            owner_menu_text(),
            reply_markup=owner_menu_keyboard()
        )

    except Exception as e:

        print(
            f"❌ Owner Menu Back Error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Could not return to owner menu.",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# COLLECTIONS BUTTON
#
# IMPORTANT:
# This handler runs BEFORE delete.py's delcollections
# handler because of group=-10.
#
# This guarantees that whenever owner clicks
# "🧾 Collections", the owner menu back button is restored.
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delcollections$"
    ),
    group=-10
)
async def owner_collections_button(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # BUILD COLLECTION MENU
        # ====================================================

        keyboard = await database_menu_keyboard()

        # ====================================================
        # SHOW COLLECTIONS
        # ====================================================

        await query.message.edit_text(
            database_menu_text(),
            reply_markup=keyboard
        )

        # ====================================================
        # ANSWER CALLBACK
        # ====================================================

        await query.answer()

    except Exception as e:

        print(
            f"❌ Owner Collections Menu Error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Collections menu failed.",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# BROADCAST BUTTON
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^owner_broadcast$"
    )
)
async def owner_broadcast_button(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # START SAME BROADCAST STATE USED BY
        # handlers/broadcast.py
        # ====================================================

        owner_id = query.from_user.id

        pending_broadcasts[
            owner_id
        ] = None

        # ====================================================
        # CALLBACK ANSWER
        # ====================================================

        await query.answer(
            "📢 Broadcast mode started."
        )

        # ====================================================
        # SAME PROMPT AS /broadcast
        # ====================================================

        await query.message.reply_text(
            "📢 Send the message to broadcast."
        )

        print(
            f"📢 Broadcast started from owner menu: "
            f"{owner_id}",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Owner Broadcast Button Error: {e}",
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
# REINDEX BUTTON
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^owner_reindex$"
    )
)
async def owner_reindex_button(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # CALLBACK ANSWER
        # ====================================================

        await query.answer(
            "♻️ Reindexing..."
        )

        # ====================================================
        # STATUS MESSAGE
        # ====================================================

        status = await query.message.reply_text(
            "♻️ **Reindexing channel files...**"
        )

        try:

            # ====================================================
            # REINDEX
            # ====================================================

            count = await reindex_channel(
                client
            )

            # ====================================================
            # REINDEX SUCCESS
            # ====================================================

            await status.edit_text(
                f"""
♻️ **Reindex Complete**

🎬 **Indexed Files:** `{count}`
"""
            )

            # ====================================================
            # OWNER LOG
            # ====================================================

            try:

                await send_log(
                    f"""
♻️ <b>Reindex Completed</b>

👤 <b>Owner:</b>
<code>{query.from_user.id}</code>

📦 <b>Indexed Files:</b>
<code>{count}</code>
"""
                )

            except Exception as log_error:

                print(
                    f"⚠️ Reindex Log Error: {log_error}",
                    flush=True
                )

        except Exception as e:

            print(
                f"❌ Reindex Button Error: {e}",
                flush=True
            )

            try:

                await status.edit_text(
                    f"""
❌ **Reindex Failed**

⚠️ **Error:**
`{type(e).__name__}: {e}`
"""
                )

            except Exception:
                pass

    except Exception as e:

        print(
            f"❌ Reindex Callback Error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Reindex failed",
                show_alert=True
            )

        except Exception:
            pass


# ============================================================
# RELOAD BUTTON
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^owner_reload$"
    )
)
async def owner_reload_button(
    client,
    query: CallbackQuery
):

    try:

        # ====================================================
        # OWNER CHECK
        # ====================================================

        if not await check_callback_owner(
            query
        ):

            return

        # ====================================================
        # CALLBACK ANSWER
        # ====================================================

        await query.answer(
            "♻️ Reloading..."
        )

        # ====================================================
        # STATUS MESSAGE
        # ====================================================

        status = await query.message.reply_text(
            "♻️ **Reloading configuration...**"
        )

        try:

            # ====================================================
            # RELOAD CONFIGURATION
            # ====================================================

            import config

            importlib.reload(
                config
            )

            # ====================================================
            # RELOAD SUCCESS
            # ====================================================

            await status.edit_text(
                """
♻️ **Configuration Reloaded**

✅ Reload completed successfully.
"""
            )

            # ====================================================
            # OWNER LOG
            # ====================================================

            try:

                await send_log(
                    f"""
♻️ <b>Configuration Reloaded</b>

👤 <b>Owner:</b>
<code>{query.from_user.id}</code>
"""
                )

            except Exception as log_error:

                print(
                    f"⚠️ Reload Log Error: {log_error}",
                    flush=True
                )

        except Exception as e:

            print(
                f"❌ Reload Button Error: {e}",
                flush=True
            )

            try:

                await status.edit_text(
                    f"""
❌ **Reload Failed**

⚠️ **Error:**
`{type(e).__name__}: {e}`
"""
                )

            except Exception:
                pass

    except Exception as e:

        print(
            f"❌ Reload Callback Error: {e}",
            flush=True
        )

        try:

            await query.answer(
                "❌ Reload failed",
                show_alert=True
            )

        except Exception:
            pass
