from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# ---------------- START / HOME BUTTONS ---------------- #

def start_buttons(bot_username: str = None):
    """
    Main /start and Home keyboard.

    Row 1:
        ➕ Add to Group | 🔍 Search Movies

    Row 2:
        📢 Updates

    Row 3:
        ☺️ About
    """
    # Create the deep-link URL for adding the bot to a group
    add_group_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add to Group",
                    url=add_group_url
                ),
                InlineKeyboardButton(
                    "🔍 Search Movies",
                    switch_inline_query_current_chat=""
                )
            ],
            [
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
