import asyncio

from pyrogram import filters
from pyrogram.types import Message

from bot import app

from filters.owner import owner_filter

from utils.logger import send_log
from utils.reindex import reindex_channel


# ---------------- REINDEX ----------------


@app.on_message(filters.command("reindex") & owner_filter)
async def reindex_command(client, message: Message):

    status = await message.reply_text(
        "♻️ Reindexing channel files..."
    )

    try:

        count = await reindex_channel(
            client
        )

        await status.edit_text(
            f"""
✅ Reindex Complete

🎬 Indexed Files: <code>{count}</code>
"""
        )

        await asyncio.sleep(
            10
        )

        try:

            await status.delete()

        except Exception as delete_error:

            print(
                f"⚠️ Reindex message delete error: "
                f"{delete_error}",
                flush=True
            )

        await send_log(
            f"""
♻️ <b>Reindex Completed</b>
👤 Owner:
<code>{message.from_user.id}</code>
📦 Indexed Files:
<code>{count}</code>
"""
        )

    except Exception as e:

        await status.edit_text(
            f"""
❌ Reindex Failed

Error:
{e}
"""
        )


# ---------------- RELOAD ----------------


@app.on_message(filters.command("reload") & owner_filter)
async def reload_command(client, message: Message):

    status = await message.reply_text(
        "♻️ Reloading..."
    )

    try:

        await status.edit_text(
            """
♻️ Configuration reloaded.
"""
        )

        await asyncio.sleep(
            10
        )

        try:

            await status.delete()

        except Exception as delete_error:

            print(
                f"⚠️ Reload message delete error: "
                f"{delete_error}",
                flush=True
            )

    except Exception as e:

        await status.edit_text(
            f"""
❌ Reload Failed

Error:
{e}
"""
        )
