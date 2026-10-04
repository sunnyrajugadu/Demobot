from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# ---------------- START / HOME BUTTONS ---------------- #

def start_buttons(bot_username: str = None):
    """
    Main /start and Home keyboard.

    Row 1:
        ➕ Add Me to Your Groups

    Row 2:
        🔍 Search Movies | 📢 Updates

    Row 3:
        ☺️ About
    """
    # Create the deep-link URL for adding the bot to a group with automatic admin permissions pre-selected
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
                    "🔍 Search Movies",
                    switch_inline_query_current_chat=""
                ),
                InlineKeyboardButton(
                    "📢 Updates",
                    url="https://t.me/mrDuDeHoLic"
                )
            ],
            [
                InlineKeyboardButton(
                    "☺️ About",
                    callback_data="home_about"
                )
            ]
        ]
    )


# ---------------- ABOUT BUTTONS ---------------- #

def about_buttons():
    """
    About page keyboard.
    """

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏠 Home",
                    callback_data="home_main"
                )
            ]
        ]
    )


# ---------------- MOVIE BUTTONS ---------------- #

def movie_buttons(file_buttons):
    """
    Movie / file selection keyboard.
    """
    return InlineKeyboardMarkup(file_buttons)
