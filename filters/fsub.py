# filters/fsub.py
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

from config import AUTH_CHANNEL, CHANNEL_INVITE_LINK

# ================= FSUB CONSTANTS ================= #
FSUB_CAPTION = "❗**You must join our channel before using this feature.**"
FSUB_ALERT = "I Like Your Smartness, But Don't Be Oversmart Okay 😒"


# ================= MEMBERSHIP VERIFIER ================= #
async def is_subscribed(client, user_id: int) -> bool:
    if not AUTH_CHANNEL:
        return True

    try:
        target_chat = AUTH_CHANNEL
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
        print(f"❌ FSUB ERROR for User {user_id} in {AUTH_CHANNEL}: {e}", flush=True)
        return False


# ================= BUTTON GENERATOR ================= #
def get_fsub_buttons(message_id: int, payload: str = "") -> InlineKeyboardMarkup:
    safe_query = (payload or "")[:35]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Main Channel", url=CHANNEL_INVITE_LINK)],
        [InlineKeyboardButton("Try Again", callback_data=f"fsub_retry:{message_id}:{safe_query}")]
    ])


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
