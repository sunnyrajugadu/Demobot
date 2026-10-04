import io
import asyncio
import aiohttp

from pyrogram import filters
from pyrogram.types import Message, ChatMemberUpdated, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import app

print(
    "✅ group.py imported",
    flush=True
)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def group_start_buttons(bot_username: str = None):
    """
    Group specific start keyboard layout:
    Row 1: Add Me to Your Groups
    Row 2: Updates
    """
    if bot_username:
        add_group_url = f"https://t.me/{bot_username}?startgroup=true&admin=change_info+delete_messages+invite_users+pin_messages"
    else:
        add_group_url = "https://t.me/"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add Me to Your Groups",
                    url=add_group_url
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Updates",
                    url="https://t.me/mrDuDeHoLic"
                )
            ]
        ]
    )


async def delete_message_after_delay(message: Message, delay: int = 30):
    """Deletes a message automatically after 30 seconds."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


# ============================================================
# BOT ADDED TO GROUP WATCHER (WELCOME & ADMIN CHECK - 30s DELETE)
# ============================================================

@app.on_chat_member_updated()
async def bot_added_to_group(client, chat_member_updated: ChatMemberUpdated):
    """Handles when the bot is added to a group via the Add to Group button."""
    try:
        new_member = chat_member_updated.new_chat_member
        if new_member and new_member.user.id == (await client.get_me()).id:
            chat = chat_member_updated.chat
            
            if new_member.status in ["administrator", "creator"]:
                text = (
                    f"🎉 • Tʜᴀɴᴋ Yᴏᴜ Fᴏʀ Aᴅᴅɪɴɢ Mᴇ Tᴏ <b>{chat.title}</b>!\n\n"
                    "🔰 • I Aᴍ Sᴜᴄᴄᴇssғᴜʟʟʏ Cᴏɴғɪɢᴜʀᴇᴅ As Aɴ Aᴅᴍɪɴɪsᴛʀᴀᴛᴏʀ ✅.\n"
                    "⚡ • Yᴏᴜ Cᴀɴ Nᴏᴡ Sᴇᴀʀᴄʜ Fᴏʀ Mᴏᴠɪᴇs Hᴇʀᴇ 🎬."
                )

            else:
                text = (
                    f"🌹• Hᴇʟʟᴏ Eᴠᴇʀʏᴏɴᴇ Iɴ <b>{chat.title}</b>! 💫\n\n"
                    "🔰 • Pʟᴇᴀsᴇ Pʀᴏᴍᴏᴛᴇ Mᴇ As Aɴ Aᴅᴍɪɴɪsᴛʀᴀᴛᴏʀ 🌞.\n"
                    "⚡ • Sᴏ Tʜᴀᴛ I Cᴀɴ Fᴜɴᴄᴛɪᴏɴ Pʀᴏᴘᴇʀʟʏ Aɴᴅ Hᴇʟᴘ Yᴏᴜ Sᴇᴀʀᴄʜ Mᴏᴠɪᴇs Eғғɪᴄɪᴇɴᴛʟʏ🎬."
                )

            
            sent_msg = await client.send_message(chat.id, text)
            if sent_msg:
                asyncio.create_task(delete_message_after_delay(sent_msg, 30))
    except Exception as e:
        print(f"[group watcher error] {e}", flush=True)


# ============================================================
# GROUP /START COMMAND HANDLER (30s AUTO DELETE)
# ============================================================

@app.on_message(
    filters.group & filters.command("start")
)
async def group_start_command(client, message: Message):
    print("GROUP START HANDLER CALLED", flush=True)

    bot_info = await client.get_me()
    bot_username = bot_info.username if bot_info else None

    text = (
        f"🌹• Hᴇʟʟᴏ Eᴠᴇʀʏᴏɴᴇ Iɴ <b>{message.chat.title}</b>! 💫\n\n"
        "🎥 • Wᴇʟᴄᴏᴍᴇ Tᴏ <b>CɪɴᴇᴍᴀVᴇᴛᴀ Gʀᴏᴜᴘ Sᴇᴀʀᴄʜ</b>🍿\n"
        "⚡ • Sᴇᴀʀᴄʜ Yoᴜʀ Fᴀᴠᴏʀɪᴛᴇ Mᴏᴠɪᴇs & Sᴇʀɪᴇs Rɪɢʜᴛ Hᴇʀᴇ 🎬.\n\n"
    )


    markup = group_start_buttons(bot_username)

    sent_msg = await message.reply_text(
        text=text,
        reply_markup=markup,
        quote=True
    )
    if sent_msg:
        asyncio.create_task(delete_message_after_delay(sent_msg, 30))


# ============================================================
# CALLBACK QUERY HANDLER FOR GROUP HOME (PREVENTS INLINE QUERY BUG)
# ============================================================

@app.on_callback_query(filters.regex("^home_main$"))
async def group_home_callback(client, callback_query: CallbackQuery):
    """Handles home callback specifically for groups so it restores group buttons instead of private inline buttons."""
    message = callback_query.message
    if message and message.chat.type in ["group", "supergroup"]:
        bot_info = await client.get_me()
        bot_username = bot_info.username if bot_info else None

        text = (
            f"🌹• Hᴇʟʟᴏ Eᴠᴇʀʏᴏɴᴇ Iɴ <b>{message.chat.title}</b>! 💫\n\n"
            "🎥 • Wᴇʟᴄᴏᴍᴇ Tᴏ <b>CɪɴᴇᴍᴀVᴇᴛᴀ Gʀᴏᴜᴘ Sᴇᴀʀᴄʜ</b>🍿\n"
            "⚡ • Sᴇᴀʀᴄʜ Yoᴜʀ Fᴀᴠᴏʀɪᴛᴇ Mᴏᴠɪᴇs & Sᴇʀɪᴇs Rɪɢʜᴛ Hᴇʀᴇ 🎬. \n\n"
        )


        markup = group_start_buttons(bot_username)

        try:
            if message.photo:
                await message.edit_caption(caption=text, reply_markup=markup)
            else:
                await message.edit_text(text=text, reply_markup=markup)
        except Exception:
            pass
        
        await callback_query.answer()
