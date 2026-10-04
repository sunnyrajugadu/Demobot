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
    Row 2: Updates | About
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
                ),
                InlineKeyboardButton(
                    "☺️ About",
                    callback_data="home_about"
                )
            ]
        ]
    )


# ============================================================
# BOT ADDED TO GROUP WATCHER (WELCOME & ADMIN CHECK)
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
                    f"✦ thank you for adding me to <b>{chat.title}</b>.\n\n"
                    "i am successfully configured as an administrator. "
                    "you can now search for movies here."
                )
            else:
                text = (
                    f"✦ hello everyone in <b>{chat.title}</b>.\n\n"
                    "please promote me as an administrator so i can function properly "
                    "and help you search movies efficiently."
                )
            
            await client.send_message(chat.id, text)
    except Exception as e:
        print(f"[group watcher error] {e}", flush=True)


# ============================================================
# GROUP /START COMMAND HANDLER (TEXT ONLY, NO IMAGES)
# ============================================================

@app.on_message(
    filters.group & filters.command("start")
)
async def group_start_command(client, message: Message):
    print("GROUP START HANDLER CALLED", flush=True)

    bot_info = await client.get_me()
    bot_username = bot_info.username if bot_info else None

    text = (
        f"✦ hello everyone in <b>{message.chat.title}</b>.\n\n"
        "• search your favorite movies & series easily right here."
    )

    markup = group_start_buttons(bot_username)

    await message.reply_text(
        text=text,
        reply_markup=markup,
        quote=True
    )


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
            f"✦ hello everyone in <b>{message.chat.title}</b>.\n\n"
            "• search your favorite movies & series easily right here."
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
