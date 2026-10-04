from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# ---------------- START / HOME BUTTONS ---------------- #

def start_buttons(bot_username: str = None):
    """
    Main /start and Home keyboard.

    Row 1:
        🔍 Search | 📢 Updates

    Row 2:
        ☺️ About
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔍 Search Movies", switch_inline_query_current_chat=""),

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
