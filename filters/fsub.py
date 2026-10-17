# filters/fsub.py
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

from config import (
    AUTH_CHANNEL,
    CHANNEL_INVITE_LINK,
    AUTH_CHANNEL_2,
    CHANNEL_INVITE_LINK_2,
)

# ================= FSUB CONSTANTS ================= #
FSUB_CAPTION = "❗**You must join our channels before using this feature.**"
FSUB_ALERT = "I Like Your Smartness, But Don't Be Oversmart Okay 😒"


# ================= SINGLE CHANNEL CHECKER ================= #
async def _check_single_channel(client, chat_id, user_id: int) -> bool:
    if not chat_id:
        return True

    try:
        target_chat = chat_id
        if isinstance(target_chat, str):
            target_chat = target_chat.strip()
            if target_chat.startswith("-100") and target_chat[4:].isdigit():
                target_chat = int(target_chat)
            elif target_chat.isdigit():
                target_chat = int(target_chat)

        member = await client.get_chat_member(chat_id=target_chat, user_id=user_id)

        if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT, "kicked", "left"]:
            return False

        return True

    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"❌ FSUB ERROR for User {user_id} in {chat_id}: {e}", flush=True)
        return False


# ================= MEMBERSHIP VERIFIER ================= #
async def is_subscribed(client, user_id: int) -> bool:
    for channel in (AUTH_CHANNEL, AUTH_CHANNEL_2):
        if channel:
            if not await _check_single_channel(client, channel, user_id):
                return False
    return True


# ================= BUTTON GENERATOR ================= #
def get_fsub_buttons(message_id: int, payload: str = "") -> InlineKeyboardMarkup:
    safe_query = (payload or "")[:35]
    buttons = []

    if CHANNEL_INVITE_LINK:
        buttons.append([InlineKeyboardButton("Join Channel", url=CHANNEL_INVITE_LINK)])

    if CHANNEL_INVITE_LINK_2:
        buttons.append([InlineKeyboardButton("Join Channel", url=CHANNEL_INVITE_LINK_2)])

    buttons.append([InlineKeyboardButton("Try Again", callback_data=f"fsub_retry:{message_id}:{safe_query}")])
    return InlineKeyboardMarkup(buttons)


# ================= ENFORCE FSUB PROMPT ================= #
async def enforce_fsub(client, message: Message, payload: str = "") -> bool:
    """
    Checks subscription. If not subscribed, sends quote reply prompt with buttons.
    Returns:
        True -> User is subscribed (allow request)
        False -> Blocked & prompted to join (halt execution)
    """
    if not message.from_user:
        return True

    user_id = message.from_user.id
    if await is_subscribed(client, user_id):
        return True

    await message.reply_text(
        text=FSUB_CAPTION,
        reply_markup=get_fsub_buttons(message.id, payload),
        quote=True
    )
    return False
