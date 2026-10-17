# filters/fsub.py
import pyrogram.utils
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

from config import (
    AUTH_CHANNEL,
    CHANNEL_INVITE_LINK,
    AUTH_CHANNEL_2,
    CHANNEL_INVITE_LINK_2,
)

# Fix Pyrogram Peer ID invalid bug for newer 10-digit channel IDs
pyrogram.utils.MIN_CHANNEL_ID = -100999999999999

# ================= FSUB CONSTANTS ================= #
FSUB_CAPTION = "❗**You must join our channels before using this feature.**"
FSUB_ALERT = "I Like Your Smartness, But Don't Be Oversmart Okay 😒"
FSUB_SUCCESS_ALERT = "✅ Thank you for joining our channels!"

# Cache to store fetched channel titles and latest unjoined channels
_CHANNEL_TITLES = {}
_LAST_UNJOINED = None


# ================= HELPER: PARSE CHAT ID ================= #
def _parse_chat_id(chat_id):
    if isinstance(chat_id, str):
        chat_id = chat_id.strip()
        if chat_id.startswith("-100") and chat_id[4:].isdigit():
            return int(chat_id)
        elif chat_id.startswith("-") and chat_id[1:].isdigit():
            return int(chat_id)
        elif chat_id.isdigit():
            return int(chat_id)
    return chat_id


# ================= SINGLE CHANNEL CHECKER ================= #
async def _check_single_channel(client, chat_id, user_id: int) -> bool:
    if not chat_id:
        return True

    target_chat = _parse_chat_id(chat_id)

    # Fetch and cache channel title if not cached yet
    if target_chat not in _CHANNEL_TITLES:
        try:
            chat = await client.get_chat(target_chat)
            if chat and chat.title:
                _CHANNEL_TITLES[target_chat] = chat.title
        except Exception as e:
            print(f"❌ FSUB CHAT TITLE ERROR in {chat_id}: {e}", flush=True)

    try:
        member = await client.get_chat_member(chat_id=target_chat, user_id=user_id)

        if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT, "kicked", "left"]:
            return False

        return True

    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"❌ FSUB ERROR for User {user_id} in {chat_id}: {e}", flush=True)
        return False


# ================= UNJOINED CHANNELS FINDER ================= #
async def get_unjoined_channels(client, user_id: int) -> list:
    """Returns a list of (channel_title, invite_link) for channels the user has NOT joined."""
    global _LAST_UNJOINED
    unjoined = []

    if AUTH_CHANNEL and CHANNEL_INVITE_LINK:
        if not await _check_single_channel(client, AUTH_CHANNEL, user_id):
            ch1_id = _parse_chat_id(AUTH_CHANNEL)
            ch1_name = _CHANNEL_TITLES.get(ch1_id, "Channel 1")
            unjoined.append((ch1_name, CHANNEL_INVITE_LINK))

    if AUTH_CHANNEL_2 and CHANNEL_INVITE_LINK_2:
        if not await _check_single_channel(client, AUTH_CHANNEL_2, user_id):
            ch2_id = _parse_chat_id(AUTH_CHANNEL_2)
            ch2_name = _CHANNEL_TITLES.get(ch2_id, "Channel 2")
            unjoined.append((ch2_name, CHANNEL_INVITE_LINK_2))

    _LAST_UNJOINED = unjoined
    return unjoined


# ================= MEMBERSHIP VERIFIER ================= #
async def is_subscribed(client, user_id: int) -> bool:
    unjoined = await get_unjoined_channels(client, user_id)
    return len(unjoined) == 0


# ================= BUTTON GENERATOR ================= #
def get_fsub_buttons(message_id: int, payload: str = "", unjoined: list = None) -> InlineKeyboardMarkup:
    safe_query = (payload or "")[:35]
    buttons = []
    first_row = []

    target_unjoined = unjoined if unjoined is not None else _LAST_UNJOINED

    if target_unjoined is not None:
        for ch_name, invite_link in target_unjoined:
            first_row.append(InlineKeyboardButton(ch_name, url=invite_link))
    else:
        if CHANNEL_INVITE_LINK:
            ch1_id = _parse_chat_id(AUTH_CHANNEL)
            ch1_name = _CHANNEL_TITLES.get(ch1_id, "Channel 1")
            first_row.append(InlineKeyboardButton(ch1_name, url=CHANNEL_INVITE_LINK))

        if CHANNEL_INVITE_LINK_2:
            ch2_id = _parse_chat_id(AUTH_CHANNEL_2)
            ch2_name = _CHANNEL_TITLES.get(ch2_id, "Channel 2")
            first_row.append(InlineKeyboardButton(ch2_name, url=CHANNEL_INVITE_LINK_2))

    if first_row:
        buttons.append(first_row)

    buttons.append([InlineKeyboardButton("Try Again", callback_data=f"fsub_retry:{message_id}:{safe_query}")])
    return InlineKeyboardMarkup(buttons)


# ================= ENFORCE FSUB PROMPT ================= #
async def enforce_fsub(client, message: Message, payload: str = "") -> bool:
    """
    Checks subscription. If not subscribed, sends quote reply prompt with buttons
    ONLY for the channels the user has not joined yet.
    Returns:
        True -> User is subscribed (allow request)
        False -> Blocked & prompted to join (halt execution)
    """
    if not message.from_user:
        return True

    user_id = message.from_user.id
    unjoined = await get_unjoined_channels(client, user_id)

    if not unjoined:
        return True

    await message.reply_text(
        text=FSUB_CAPTION,
        reply_markup=get_fsub_buttons(message.id, payload, unjoined=unjoined),
        quote=True
    )
    return False
