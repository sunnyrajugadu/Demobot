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

from database import get_database


print(
    "✅ delete.py imported",
    flush=True
)


# ============================================================
# SETTINGS
# ============================================================

ITEMS_PER_PAGE = 8


# ============================================================
# GET COLLECTIONS
# ============================================================

async def get_collections():

    database = get_database()

    names = await database.list_collection_names()

    return sorted(
        names
    )


# ============================================================
# COLLECTION MENU
# ============================================================

async def collection_menu():

    collections = await get_collections()

    buttons = []


    for name in collections:

        buttons.append(
            [
                InlineKeyboardButton(
                    f"{name}",
                    callback_data=f"delcol:{name}"
                )
            ]
        )


    if not buttons:

        buttons.append(
            [
                InlineKeyboardButton(
                    "📭 No Collections",
                    callback_data="delete_noop"
                )
            ]
        )


    return InlineKeyboardMarkup(
        buttons
    )


# ============================================================
# /DELETE
# ============================================================

@app.on_message(
    filters.command("delete") & owner_filter
)
async def delete_command(
    client,
    message: Message
):

    await message.reply_text(
        """
🔰 **Database Manager**

━━━━━━━━━━━━━━━━━━━━━━━━

Select a collection:
""",
        reply_markup=await collection_menu()
    )


# ============================================================
# COLLECTION ITEMS
# ============================================================

async def collection_items(
    collection_name,
    page=0
):

    database = get_database()

    collection = database[
        collection_name
    ]


    total = await collection.count_documents({})


    skip = page * ITEMS_PER_PAGE


    documents = []

    cursor = collection.find(
        {}
    ).skip(
        skip
    ).limit(
        ITEMS_PER_PAGE
    )


    async for document in cursor:

        documents.append(
            document
        )


    return (
        documents,
        total
    )


# ============================================================
# ITEM NAME
# ============================================================

def get_item_name(
    document
):

    if document.get(
        "movie_name"
    ):

        return str(
            document["movie_name"]
        )[:45]


    if document.get(
        "file_name"
    ):

        return str(
            document["file_name"]
        )[:45]


    if document.get(
        "username"
    ):

        return str(
            document["username"]
        )[:45]


    if document.get(
        "user_id"
    ):

        return f"User {document['user_id']}"


    if document.get(
        "search_id"
    ):

        return f"Search {document['search_id']}"


    if document.get(
        "_id"
    ):

        return str(
            document["_id"]
        )[:45]


    return "Unknown Record"


# ============================================================
# BUILD ITEMS MENU
# ============================================================

async def build_items_menu(
    collection_name,
    page=0
):

    documents, total = await collection_items(
        collection_name,
        page
    )


    buttons = []


    for document in documents:

        document_id = str(
            document["_id"]
        )


        name = get_item_name(
            document
        )


        buttons.append(
            [
                InlineKeyboardButton(
                    f"{name}",
                    callback_data=(
                        f"deldoc:{collection_name}:"
                        f"{document_id}:{page}"
                    )
                )
            ]
        )


    # ========================================================
    # DELETE ALL
    # ========================================================

    if total > 0:

        buttons.append(
            [
                InlineKeyboardButton(
                    "⚠️ Delete All",
                    callback_data=(
                        f"delall:{collection_name}"
                    )
                )
            ]
        )


    # ========================================================
    # PAGINATION
    # ========================================================

    navigation = []


    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "◀️ Previous",
                callback_data=(
                    f"delpage:{collection_name}:"
                    f"{page - 1}"
                )
            )
        )


    if (
        (page + 1) * ITEMS_PER_PAGE
        < total
    ):

        navigation.append(
            InlineKeyboardButton(
                "Next ▶️",
                callback_data=(
                    f"delpage:{collection_name}:"
                    f"{page + 1}"
                )
            )
        )


    if navigation:

        buttons.append(
            navigation
        )


    buttons.append(
        [
            InlineKeyboardButton(
                "🧾 Collections",
                callback_data="delcollections"
            )
        ]
    )


    return InlineKeyboardMarkup(
        buttons
    )


# ============================================================
# COLLECTION SELECT
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delcol:"
    )
)
async def collection_select(
    client,
    query: CallbackQuery
):

    if (
        not query.from_user
        or query.from_user.id
        != __import__("config").OWNER_ID
    ):

        await query.answer(
            "❌ You're not the owner!",
            show_alert=True
        )

        return


    collection_name = (
        query.data.split(
            ":",
            1
        )[1]
    )


    try:

        keyboard = await build_items_menu(
            collection_name,
            0
        )


        await query.message.edit_text(
            f"""
📄 **Collection:** `{collection_name}`

━━━━━━━━━━━━━━━━━━━━━━━━

Select a record to delete:
""",
            reply_markup=keyboard
        )


        await query.answer()


    except Exception as e:

        await query.answer(
            "❌ Unable to open collection.",
            show_alert=True
        )


        print(
            f"❌ Collection Select Error: {e}",
            flush=True
        )


# ============================================================
# PAGINATION
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delpage:"
    )
)
async def delete_page(
    client,
    query: CallbackQuery
):

    try:

        _, collection_name, page = (
            query.data.split(
                ":"
            )
        )


        page = int(
            page
        )


        keyboard = await build_items_menu(
            collection_name,
            page
        )


        await query.message.edit_reply_markup(
            keyboard
        )


        await query.answer()


    except Exception as e:

        print(
            f"❌ Delete Page Error: {e}",
            flush=True
        )


        await query.answer(
            "❌ Unable to load page.",
            show_alert=True
        )


# ============================================================
# DELETE SINGLE DOCUMENT
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^deldoc:"
    )
)
async def delete_document(
    client,
    query: CallbackQuery
):

    try:

        if (
            not query.from_user
            or query.from_user.id
            != __import__("config").OWNER_ID
        ):

            await query.answer(
                "❌ You're not the owner!",
                show_alert=True
            )

            return


        parts = query.data.split(
            ":"
        )


        collection_name = parts[1]

        document_id = parts[2]

        page = int(
            parts[3]
        )


        from bson import ObjectId


        database = get_database()

        collection = database[
            collection_name
        ]


        result = await collection.delete_one(
            {
                "_id": ObjectId(
                    document_id
                )
            }
        )


        if result.deleted_count:

            await query.answer(
                "✅ Deleted"
            )

        else:

            await query.answer(
                "⚠️ Record not found.",
                show_alert=True
            )


        # ====================================================
        # REFRESH REMAINING RECORDS
        # ====================================================

        documents, total = await collection_items(
            collection_name,
            page
        )


        if (
            not documents
            and page > 0
        ):

            page -= 1


        keyboard = await build_items_menu(
            collection_name,
            page
        )


        await query.message.edit_reply_markup(
            keyboard
        )


    except Exception as e:

        print(
            f"❌ Delete Document Error: {e}",
            flush=True
        )


        await query.answer(
            "❌ Delete failed.",
            show_alert=True
        )


# ============================================================
# DELETE ALL CONFIRMATION
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delall:"
    )
)
async def delete_all_confirmation(
    client,
    query: CallbackQuery
):

    try:

        if (
            not query.from_user
            or query.from_user.id
            != __import__("config").OWNER_ID
        ):

            await query.answer(
                "❌ You're not the owner!",
                show_alert=True
            )

            return


        collection_name = (
            query.data.split(
                ":",
                1
            )[1]
        )


        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Confirm",
                        callback_data=(
                            f"confirmall:{collection_name}"
                        )
                    ),

                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data=(
                            f"cancelall:{collection_name}"
                        )
                    )
                ]
            ]
        )


        await query.message.edit_text(
            f"""
⚠️ **Delete All**

━━━━━━━━━━━━━━━━━━━━━━━━

Collection:

`{collection_name}`

Are you sure you want to delete **ALL**
records from this collection?

This action cannot be undone.
""",
            reply_markup=buttons
        )


        await query.answer()


    except Exception as e:

        print(
            f"❌ Delete All Confirmation Error: {e}",
            flush=True
        )


# ============================================================
# CONFIRM DELETE ALL
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^confirmall:"
    )
)
async def confirm_delete_all(
    client,
    query: CallbackQuery
):

    try:

        if (
            not query.from_user
            or query.from_user.id
            != __import__("config").OWNER_ID
        ):

            await query.answer(
                "❌ You're not the owner!",
                show_alert=True
            )

            return


        collection_name = (
            query.data.split(
                ":",
                1
            )[1]
        )


        database = get_database()

        collection = database[
            collection_name
        ]


        result = await collection.delete_many(
            {}
        )


        await query.answer(
            "✅ All records deleted."
        )


        await query.message.edit_text(
            f"""
✅ **Collection Cleared**

━━━━━━━━━━━━━━━━━━━━━━━━

📄 Collection:
`{collection_name}`

✅ Deleted:
`{result.deleted_count}` records

💾 No records remaining.
""",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🧾 Collections",
                            callback_data="delcollections"
                        )
                    ]
                ]
            )
        )


    except Exception as e:

        print(
            f"❌ Delete All Error: {e}",
            flush=True
        )


        await query.answer(
            "❌ Delete all failed.",
            show_alert=True
        )


# ============================================================
# CANCEL DELETE ALL
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^cancelall:"
    )
)
async def cancel_delete_all(
    client,
    query: CallbackQuery
):

    collection_name = (
        query.data.split(
            ":",
            1
        )[1]
    )


    keyboard = await build_items_menu(
        collection_name,
        0
    )


    await query.message.edit_text(
        f"""
📄 **Collection:** `{collection_name}`

━━━━━━━━━━━━━━━━━━━━━━━━

Select a record to delete:
""",
        reply_markup=keyboard
    )


    await query.answer(
        "Cancelled"
    )


# ============================================================
# BACK TO COLLECTIONS
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delcollections$"
    )
)
async def back_to_collections(
    client,
    query: CallbackQuery
):

    try:

        await query.message.edit_text(
            """
🔰 **Database Manager**

━━━━━━━━━━━━━━━━━━━━━━━━

Select a collection:
""",
            reply_markup=await collection_menu()
        )


        await query.answer()


    except Exception as e:

        print(
            f"❌ Collections Menu Error: {e}",
            flush=True
        )


# ============================================================
# NO-OP BUTTON
# ============================================================

@app.on_callback_query(
    filters.regex(
        r"^delete_noop$"
    )
)
async def delete_noop(
    client,
    query: CallbackQuery
):

    await query.answer(
        "💾 No collections available."
    )
