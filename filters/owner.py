from pyrogram import filters

from config import OWNER_ID


# ============================================================
# OWNER FILTER
# ============================================================

async def owner_filter_func(_, __, message):

    # --------------------------------------------------------
    # NO USER
    # --------------------------------------------------------

    if not message.from_user:
        return False

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    if message.from_user.id == OWNER_ID:
        return True

    # --------------------------------------------------------
    # NON-OWNER
    #
    # Silently block owner-only handlers.
    # No warning message is sent.
    # --------------------------------------------------------

    return False


# ============================================================
# PYROGRAM FILTER
# ============================================================

owner_filter = filters.create(
    owner_filter_func
)
