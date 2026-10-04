"""
Temporary catch-all handler to diagnose message reception.
Every incoming message (any type) will be logged here.
Remove this file once the /start issue is confirmed fixed.
"""
from pyrogram import filters
from pyrogram.types import Message

from bot import app


@app.on_message(filters.all, group=-1)   # group=-1 runs BEFORE all other handlers
async def debug_catch_all(client, message: Message):
    user_id = getattr(message.from_user, "id", "unknown")
    text     = getattr(message, "text", None) or getattr(message, "caption", None) or f"<{message.__class__.__name__}>"
    print(f"[DEBUG] msg received  user={user_id}  text={text!r}", flush=True)
