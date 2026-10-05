import asyncio
import time
import html
import re
from datetime import datetime
import uuid
import aiohttp
import urllib.parse
import difflib

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from bot import app
from config import LOG_CHANNEL_ID
from filters.fsub import enforce_fsub
from utils.helpers import get_imdb_suggestions, get_imdb_movie_details
from database.models import (
    search_files,
    increase_search_count,
    save_search_cache,
    update_search_state
)

print("✅ search.py imported", flush=True)


# ============================================================
# IMDB SELECTION STORAGE
# ============================================================
# Telegram callback_data has a 64-byte limit.
# So we keep the real IMDb title here and only send a short token
# inside callback_data.
#
# IMPORTANT:
# The token is NEVER used as the search query.
# When user clicks a button, the token is converted back to the
# original IMDb title and THAT TITLE is searched in database.
# ============================================================

IMDB_SELECTIONS = {}


# ================= SETTINGS =================

MENU_EXPIRE_SECONDS = 300

PAGE_LIMIT = 7

FIXED_LANGUAGES = [
    "All",
    "English",
    "Hindi",
    "Tamil",
    "Telugu",
    "Malayalam",
    "Kannada"
]

TMDB_LANG_MAP = {
    "Telugu": "te",
    "Tamil": "ta",
    "Hindi": "hi",
    "Malayalam": "ml",
    "Kannada": "kn",
    "English": "en"
}


# ================= SIZE FORMAT =================

def format_size(size):
    try:
        size = int(size or 0)
    except Exception:
        size = 0

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.2f} MB"

    if size >= 1024:
        return f"{size / 1024:.2f} KB"

    return f"{size:.0f} B"


# ================= EXTRACT AUDIO LANGUAGES =================

KNOWN_LANGS = {
    "telugu": "Telugu",
    "tamil": "Tamil",
    "hindi": "Hindi",
    "english": "English",
    "malayalam": "Malayalam",
    "kannada": "Kannada"
}


def extract_file_languages(file):
    found = set()

    for key in ("audio", "languages", "language"):
        val = file.get(key)

        if isinstance(val, list):
            for v in val:
                v_str = str(v).strip().lower()

                if v_str in KNOWN_LANGS:
                    found.add(KNOWN_LANGS[v_str])

        elif isinstance(val, str) and val:
            for word, label in KNOWN_LANGS.items():
                if re.search(
                    rf"\b{re.escape(word)}\b",
                    val,
                    re.IGNORECASE
                ):
                    found.add(label)

    text_to_scan = (
        f"{file.get('file_name', '')} "
        f"{file.get('original_file_name', '')} "
        f"{file.get('movie_name', '')}"
    )

    for word, label in KNOWN_LANGS.items():
        if re.search(
            rf"\b{re.escape(word)}\b",
            text_to_scan,
            re.IGNORECASE
        ):
            found.add(label)

    return list(found)


# ================= FILE DISPLAY NAME =================

def get_file_display_name(file):
    from utils.rename import clean_file_name

    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or ""
    )

    cleaned = clean_file_name(raw_name)

    if cleaned and cleaned.lower() != "unknown":
        return cleaned

    fallback = clean_file_name(
        file.get("movie_name") or ""
    )

    if fallback and fallback.lower() != "unknown":
        return fallback

    return "Movie"


# ============================================================
# IMDb TITLE -> DATABASE RELEASE VARIANT SEARCH
# ============================================================
#
# IMPORTANT:
# An IMDb result is the canonical movie title, NOT the exact
# filename stored in Telegram.
#
# Example IMDb title:
#     Pushpa 2: The Rule (2024)
#
# Database may contain:
#     Pushpa 2 The Rule (Reloaded Version) (2024) [Tamil].mkv
#     Pushpa 2 The Rule (2024) Telugu 720p WEBRip HEVC.mkv
#     Pushpa 2 The Rule (2024) Malayalam WEBRip x264 AA.mkv
#
# All three MUST be returned. Release tags are intentionally
# treated as extra filename metadata, not as part of the movie
# identity.
# ============================================================

SEARCH_STOP_WORDS = {
    # Common grammatical words. They are not reliable identifiers in release
    # filenames and therefore are never required for an IMDb match.
    "the", "a", "an", "of", "and", "or", "to", "in", "on",
    "for", "from", "with", "at", "by",
    # IMDb titles can use "Part 1/2", while releases often use only "1/2"
    # or omit the word completely.
    "part", "chapter", "episode",
}


def normalize_search_value(value):
    """Normalize text for movie identity matching.

    Punctuation, dots, dashes, brackets, underscores and symbols are all
    treated as separators. Therefore these are equivalent for matching:

        Pushpa - The Rise
        Pushpa. The.Rise.
        Pushpa_The_Rise
        Pushpa: The Rise
    """
    value = str(value or "").lower()

    # Replace every non-alphanumeric Unicode character with a space.
    # This deliberately ignores punctuation/symbols instead of making them
    # part of the movie identity.
    value = re.sub(r"[^\w\d]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"_+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def extract_search_year(value):
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
    return match.group(1) if match else None


def imdb_core_title(value):
    """Return canonical IMDb title without its trailing release year."""
    value = str(value or "").strip()
    value = re.sub(r"\s*\((19\d{2}|20\d{2})\)\s*$", "", value)
    value = re.sub(r"\s*[-–—]\s*(19\d{2}|20\d{2})\s*$", "", value)
    value = re.sub(r"\s+(19\d{2}|20\d{2})\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def movie_text_for_matching(file):
    return normalize_search_value(
        " ".join(
            str(file.get(key) or "")
            for key in (
                "movie_name",
                "file_name",
                "original_file_name",
                "caption"
            )
        )
    )


def movie_years(file):
    years = set()

    for key in (
        "year",
        "movie_name",
        "file_name",
        "original_file_name",
        "caption"
    ):
        value = file.get(key)
        if isinstance(value, (list, tuple, set)):
            value = " ".join(str(x) for x in value)

        for year in re.findall(
            r"\b(19\d{2}|20\d{2})\b",
            str(value or "")
        ):
            years.add(year)

    return years


def title_tokens(title):
    """Return meaningful canonical title tokens.

    Stop words are omitted so that an IMDb title like
    "Pushpa The Rise" still matches filenames where "The" is absent.
    Numeric tokens are retained because sequel numbers are important.
    """
    normalized = normalize_search_value(imdb_core_title(title))

    return [
        token
        for token in normalized.split()
        if token not in SEARCH_STOP_WORDS
    ]


def title_match_tokens(canonical_title):
    """Build token alternatives used for release-name matching.

    This handles the common IMDb/release difference:
        IMDb:    Movie Part 2
        Release: Movie 2
        Release: Movie Part 2

    """
    tokens = title_tokens(canonical_title)
    expanded = list(tokens)

    # Numeric sequel tokens remain mandatory. "Part" itself is optional.
    return expanded


def release_variant_score(file, canonical_title, target_year=None):
    """Score one DB file against an IMDb-selected canonical title.

    Matching rules:
      * punctuation/symbols/dashes/dots are ignored
      * title can occur at the beginning, middle or end of the filename
      * release metadata after/before the title is allowed
      * "Part" is optional when a numeric sequel is present
      * all meaningful title tokens must be present (80% minimum retained)
      * selected IMDb year is strict when available
    """
    text = movie_text_for_matching(file)
    if not text:
        return 0

    canonical_normalized = normalize_search_value(
        imdb_core_title(canonical_title)
    )
    tokens = title_match_tokens(canonical_title)

    if not canonical_normalized or not tokens:
        return 0

    # Strongest match: normalized canonical title appears as a contiguous
    # phrase anywhere in the stored filename. This naturally handles:
    #   "Pushpa - The Rise"
    #   "Pushpa. The.Rise. Part 1"
    phrase_match = canonical_normalized in text

    matched_tokens = 0
    for token in tokens:
        if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
            matched_tokens += 1

    coverage = matched_tokens / len(tokens)

    # A title match must contain the meaningful identity tokens. This keeps
    # short/common words from returning unrelated movies.
    if not phrase_match and coverage < 0.80:
        return 0

    # Prefer exact normalized phrase matches, while still allowing harmless
    # release differences such as "Part 1", brackets, codec tags, etc.
    score = matched_tokens * 100
    if phrase_match:
        score += 1000

    if target_year:
        file_years = movie_years(file)

        # IMDb year is only a preference, NEVER a hard requirement.
        # TV/series releases frequently omit the original year, and episode
        # filenames may contain other years (air dates, metadata, etc.).
        # Therefore a title match must survive regardless of filename year.
        if target_year in file_years:
            score += 5000
        else:
            score += 1500

    return score


def _db_dedupe_key(row):
    row_id = str(
        row.get("_id")
        or row.get("file_unique_id")
        or row.get("file_id")
        or ""
    )

    if row_id:
        return row_id

    return (
        f"{row.get('file_name', '')}::"
        f"{row.get('file_size_bytes', row.get('file_size', 0))}"
    )


async def search_imdb_release_variants(movie_name, limit=500):
    """Find ALL release variants for the selected IMDb movie.

    The database search is deliberately broader than an exact IMDb-title
    search. We retrieve candidates using normalized title tokens and then
    perform the final identity/year check in Python. This makes punctuation,
    filename placement and release tags irrelevant to the match.
    """
    canonical = imdb_core_title(movie_name)
    target_year = extract_search_year(movie_name)

    if not canonical:
        return [], canonical, target_year

    candidates = []
    seen_ids = set()
    tokens = title_match_tokens(canonical)
    normalized_canonical = normalize_search_value(canonical)

    # Query 1: full canonical title. database.search_files() already
    # normalizes punctuation, so this is fast for the common case.
    queries = []
    if normalized_canonical:
        queries.append(normalized_canonical)

    # Query 2: meaningful tokens only. This catches filenames where IMDb's
    # grammatical words are omitted or the release adds "Part" metadata.
    compact = " ".join(tokens)
    if compact and compact not in queries:
        queries.append(compact)

    async def collect(query):
        try:
            rows = await search_files(query, limit=limit)
        except Exception as e:
            print(
                f"⚠️ IMDb variant DB search error for {query!r}: {e}",
                flush=True
            )
            return

        for row in rows or []:
            dedupe_key = _db_dedupe_key(row)
            if dedupe_key in seen_ids:
                continue

            score = release_variant_score(
                row,
                canonical,
                target_year
            )
            if score <= 0:
                continue

            seen_ids.add(dedupe_key)
            candidates.append((score, row))

    for query in queries:
        await collect(query)

    # Broad fallback: search each meaningful token individually and UNION the
    # candidates. This is important when Mongo's full-token query misses a
    # release because the title words are stored in an unusual arrangement.
    # Final scoring still requires the complete movie identity, so unrelated
    # files are rejected.
    if tokens and len(candidates) < min(20, limit):
        for token in tokens:
            if len(token) < 2:
                continue
            await collect(token)

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1].get("indexed_at", 0) or 0,
            str(item[1].get("_id") or "")
        ),
        reverse=True
    )

    return [row for _, row in candidates[:limit]], canonical, target_year


# ================= SEARCH LOG =================

async def log_search(
    client,
    user,
    search_text,
    result_count=0
):
    try:
        if not LOG_CHANNEL_ID:
            return

        username = (
            f"@{user.username}"
            if user.username
            else "N/A"
        )

        first_name = user.first_name or "N/A"

        if result_count > 0:
            result_status = (
                f"✅ <b>RESULTS FOUND:</b> "
                f"<code>{result_count}</code>"
            )
        else:
            result_status = "❌ <b>NO RESULTS FOUND</b>"

        log_text = (
            "🔍 <b>SEARCH USED</b>\n\n"
            f"👤 <b>Name:</b> {first_name}\n"
            f"📱 <b>Username:</b> {username}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"🔎 <b>Search:</b> <code>{html.escape(search_text)}</code>\n\n"
            f"{result_status}"
        )

        await client.send_message(
            LOG_CHANNEL_ID,
            log_text
        )

    except Exception as e:
        print(
            f"❌ SEARCH LOG ERROR : {e}",
            flush=True
        )


# ================= AUTO DELETE HELPER =================

async def auto_delete_message(
    message,
    delay_seconds: int = 40
):
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception:
        pass


# ================= AUTO DELETE MENU =================

async def auto_delete_menu(
    client,
    chat_id,
    message_id
):
    try:
        await asyncio.sleep(
            MENU_EXPIRE_SECONDS
        )

        await client.delete_messages(
            chat_id=chat_id,
            message_ids=message_id
        )

    except Exception:
        pass


# ================= LANGUAGE BUTTONS =================

def language_buttons(
    search_id,
    timestamp,
    selected=None
):
    buttons = []
    row = []

    for lang in FIXED_LANGUAGES:

        text = (
            f"✅ {lang}"
            if selected == lang
            else lang
        )

        row.append(
            InlineKeyboardButton(
                text,
                callback_data=(
                    f"lang:"
                    f"{lang}:"
                    f"{search_id}:"
                    f"{timestamp}"
                )
            )
        )

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return buttons


# ================= DIRECT FILE BUTTON =================

def build_file_button(
    file,
    user_id,
    timestamp
):
    display_name = get_file_display_name(file)

    file_size = format_size(
        file.get("file_size_bytes", 0)
    )

    file_id = str(
        file.get("_id")
    )

    return InlineKeyboardButton(
        text=f"{file_size} | {display_name}",
        callback_data=(
            f"file:"
            f"{user_id}:"
            f"{file_id}:"
            f"{timestamp}"
        )
    )


# ================= PAGINATION =================

def pagination_buttons(
    search_id,
    page,
    total,
    timestamp
):
    row = []

    total_pages = (
        (total + PAGE_LIMIT - 1)
        // PAGE_LIMIT
    )

    if total_pages < 1:
        total_pages = 1

    if page > 1:
        row.append(
            InlineKeyboardButton(
                "⪻ Previous",
                callback_data=(
                    f"page:"
                    f"{search_id}:"
                    f"{page - 1}:"
                    f"{timestamp}"
                )
            )
        )

    row.append(
        InlineKeyboardButton(
            f"📄 {page}/{total_pages}",
            callback_data="none"
        )
    )

    if page < total_pages:
        row.append(
            InlineKeyboardButton(
                "Next ⪼",
                callback_data=(
                    f"page:"
                    f"{search_id}:"
                    f"{page + 1}:"
                    f"{timestamp}"
                )
            )
        )

    return [row]


# ============================================================
# CLEAN IMDB TITLE
# ============================================================

def clean_imdb_title(title):
    """
    Convert IMDb suggestion into a clean searchable movie name.

    Examples:
        Avatar (2009)       -> Avatar
        Avatar - 2009       -> Avatar
        The Batman (2022)   -> The Batman
    """

    if not title:
        return ""

    title = str(title).strip()

    # Remove year in brackets
    title = re.sub(
        r"\s*\(\d{4}\)\s*$",
        "",
        title
    ).strip()

    # Remove trailing - YYYY
    title = re.sub(
        r"\s*-\s*\d{4}\s*$",
        "",
        title
    ).strip()

    return title


# ============================================================
# DISPLAY IMDb TITLE
# ============================================================

def format_imdb_button_title(title):
    if not title:
        return "Unknown"

    title = str(title).strip()

    # Make bracket year easier to read
    display_text = re.sub(
        r"\((\d{4})\)",
        r" - \1",
        title
    )

    display_text = re.sub(
        r"\s+",
        " ",
        display_text
    ).strip()

    return display_text


# ============================================================
# CREATE IMDb SELECTION BUTTONS
# ============================================================

def build_imdb_selection_buttons(
    user_id,
    titles
):
    buttons = []

    for title in titles[:8]:

        if not title:
            continue

        title = str(title).strip()

        # Short backend token only.
        # User will NEVER see this token.
        token = uuid.uuid4().hex[:12]

        IMDB_SELECTIONS[token] = title

        display_text = format_imdb_button_title(
            title
        )

        callback_data = (
            f"spell:"
            f"{user_id}:"
            f"{token}"
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    display_text[:60],
                    callback_data=callback_data
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "✘ CLOSE ✘",
                callback_data="close"
            )
        ]
    )

    return buttons


# ============================================================
# CORE SEARCH EXECUTION
# ============================================================

async def execute_search(
    client,
    user,
    chat_id,
    movie_name,
    reply_to_message_id=None,
    allow_spelling_suggestions=True
):
    start_time = time.time()
    loading_msg = None

    try:

        # ====================================================
        # 1. REACTION + LOADING
        # ====================================================

        try:
            from config import BOT_TOKEN

            reaction_url = (
                "https://api.telegram.org/"
                f"bot{BOT_TOKEN}/setMessageReaction"
            )

            reaction_payload = {
                "chat_id": chat_id,
                "message_id": reply_to_message_id,
                "reaction": [
                    {
                        "type": "emoji",
                        "emoji": "🤝"
                    }
                ],
                "is_big": True
            }

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=2.0
                )
            ) as session:

                await session.post(
                    reaction_url,
                    json=reaction_payload
                )

        except Exception:
            pass

        try:
            loading_msg = await client.send_message(
                chat_id=chat_id,
                text=(
                    f"**🔎 Searching** "
                    f"`{movie_name}` **. . .**"
                ),
                reply_to_message_id=reply_to_message_id
            )

        except Exception:
            pass

        await asyncio.sleep(1.5)

        user_id = user.id

        print(
            f"🔍 SEARCH : {movie_name}",
            flush=True
        )

        asyncio.create_task(
            increase_search_count(user_id)
        )


        # ====================================================
        # 2. YEAR DETECTION
        # ====================================================

        has_explicit_year = False
        target_year = None
        base_movie_name = movie_name

        year_match = re.search(
            r"(?:^|[-\s])(\d{4})$",
            movie_name.strip()
        )

        if year_match:

            has_explicit_year = True
            target_year = year_match.group(1)

            base_movie_name = (
                movie_name[
                    :year_match.start()
                ]
                .strip(" -")
                .strip()
            )


        # ====================================================
        # 3. IMDb VARIANTS FIRST
        # ====================================================
        #
        # For normal searches, IMDb variants are checked BEFORE
        # database search.
        #
        # Example:
        #
        # User searches:
        #     batman
        #
        # Bot may show:
        #
        #     Batman - 1943
        #     Batman - 1989
        #     Batman - 2005
        #     The Batman - 2022
        #
        # Clicking one does NOT search the UUID.
        # It searches the stored IMDb TITLE.
        # ====================================================

        imdb_suggestions = []
        if allow_spelling_suggestions:
            try:
                imdb_suggestions = (
                    await get_imdb_suggestions(
                        base_movie_name,
                        limit=8
                    )
                )
            except Exception as e:
                print(
                    f"⚠️ IMDb suggestion error: {e}",
                    flush=True
                )
                imdb_suggestions = []


        # Remove duplicate titles
        unique_suggestions = []

        seen_titles = set()

        for title in imdb_suggestions or []:

            if not title:
                continue

            title = str(title).strip()

            normalized = re.sub(
                r"[^a-z0-9]+",
                " ",
                title.lower()
            ).strip()

            if normalized in seen_titles:
                continue

            seen_titles.add(normalized)
            unique_suggestions.append(title)


        imdb_suggestions = unique_suggestions[:8]


        # ====================================================
        # 4. SHOW IMDb VARIANTS
        # ====================================================
      
        if imdb_suggestions:

            normalized_query = re.sub(
                r"[^a-z0-9 ]",
                "",
                base_movie_name.lower()
            ).strip()

            normalized_titles = []

            for title in imdb_suggestions:

                cleaned_title = clean_imdb_title(
                    title
                )

                normalized_titles.append(
                    re.sub(
                        r"[^a-z0-9 ]",
                        "",
                        cleaned_title.lower()
                    ).strip()
                )

            similarity = max(
                (
                    difflib.SequenceMatcher(
                        None,
                        normalized_query,
                        title
                    ).ratio()
                    for title in normalized_titles
                ),
                default=0.0
            )

            is_spelling_candidate = (
                bool(normalized_query)
                and similarity >= 0.72
                and normalized_query
                not in normalized_titles
            )


            suggestion_buttons = (
                build_imdb_selection_buttons(
                    user_id,
                    imdb_suggestions
                )
            )


            # ----------------------------------------------
            # Spelling mistake
            # ----------------------------------------------

            if is_spelling_candidate:

                prompt_text = (
                    f"`{movie_name}`\n\n"
                    "**Spelling Mistake Bro ‼️**\n\n"
                    "**DON'T WORRY 😊 "
                    "CHOOSE THE CORRECT ONE BELOW 👇**"
                )

            # ----------------------------------------------
            # Normal multiple IMDb results
            # ----------------------------------------------

            else:

                prompt_text = (
                    f"🎬 **Multiple movies found for:** "
                    f"`{movie_name}`\n\n"
                    "👇🏻 **Choose The Movie below 👇🏻**"
                )


            prompt_msg = await client.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=InlineKeyboardMarkup(
                    suggestion_buttons
                ),
                reply_to_message_id=reply_to_message_id
            )

            if prompt_msg:
                asyncio.create_task(
                    auto_delete_message(
                        prompt_msg,
                        delay_seconds=45
                    )
                )

            return


        # ====================================================
        # 5. DATABASE SEARCH
        # ====================================================
        #
        # Normal user text keeps the existing fast search behaviour.
        # IMDb-selected titles use release-variant matching so that
        # filenames containing extra release tags are NOT rejected.
        # ====================================================

        if allow_spelling_suggestions is False:
            results, selected_canonical_title, selected_year = (
                await search_imdb_release_variants(
                    movie_name,
                    limit=500
                )
            )

            if selected_canonical_title:
                imdb_search_query = selected_canonical_title

            if selected_year:
                has_explicit_year = True
                target_year = selected_year
        else:
            results = await search_files(
                movie_name,
                limit=500
            )

            # Existing fallback: Movie - Year -> Movie
            if not results and "-" in movie_name:
                clean_name = (
                    movie_name
                    .split("-")[0]
                    .strip()
                )

                if clean_name:
                    results = await search_files(
                        clean_name,
                        limit=500
                    )

        # ====================================================
        # 6. STRICT YEAR FILTER FOR NORMAL SEARCHES
        # ====================================================
        # IMDb-selected searches already enforce the selected year inside
        # search_imdb_release_variants(). Do not apply a second lossy filter.
        # ====================================================

        if (
            allow_spelling_suggestions is not False
            and has_explicit_year
            and target_year
        ):
            filtered_results = []

            for f in results:
                f_name = (
                    f.get("movie_name")
                    or f.get("file_name")
                    or ""
                )
                f_year = str(f.get("year", ""))

                if (
                    target_year in f_name
                    or target_year == f_year
                ):
                    filtered_results.append(f)

            if filtered_results:
                results = filtered_results


        # ====================================================
        # 7. SEARCH LOG
        # ====================================================

        asyncio.create_task(
            log_search(
                client,
                user,
                movie_name,
                len(results) if results else 0
            )
        )


        # ====================================================
        # 8. NO DATABASE RESULTS
        # ====================================================

        if not results:

            # ----------------------------------------------
            # IMDb spelling suggestions
            # ----------------------------------------------

            if allow_spelling_suggestions:

                try:
                    suggestions = (
                        await get_imdb_suggestions(
                            movie_name,
                            limit=8
                        )
                    )
                except Exception:
                    suggestions = []

                unique_no_result_suggestions = []

                seen = set()

                for title in suggestions or []:

                    if not title:
                        continue

                    title = str(title).strip()

                    key = re.sub(
                        r"[^a-z0-9]+",
                        " ",
                        title.lower()
                    ).strip()

                    if key in seen:
                        continue

                    seen.add(key)
                    unique_no_result_suggestions.append(
                        title
                    )

                suggestions = (
                    unique_no_result_suggestions[:8]
                )


                if suggestions:

                    suggestion_buttons = (
                        build_imdb_selection_buttons(
                            user_id,
                            suggestions
                        )
                    )

                    reply_text = (
                        f"`{movie_name}`\n\n"
                        "**Spelling Mistake Bro ‼️**\n\n"
                        "**DON'T WORRY 😊 "
                        "CHOOSE THE CORRECT ONE BELOW 👇**"
                    )

                    spell_msg = await client.send_message(
                        chat_id=chat_id,
                        text=reply_text,
                        reply_markup=InlineKeyboardMarkup(
                            suggestion_buttons
                        ),
                        reply_to_message_id=reply_to_message_id
                    )

                    if spell_msg:
                        asyncio.create_task(
                            auto_delete_message(
                                spell_msg,
                                delay_seconds=30
                            )
                        )

                    return


            # ----------------------------------------------
            # GOOGLE FALLBACK
            # ----------------------------------------------

            google_query = urllib.parse.quote_plus(
                movie_name
            )

            google_search_url = (
                "https://www.google.com/search"
                f"?q={google_query}"
            )


            no_result_text = (
                f'✨ **Oops! I couldn\'t find '
                f'"{movie_name}" in my database** 📀\n\n'
                "🔍 **Search on Google and check "
                "if your spelling is correct.**\n\n"
                "📖 **Please read the instructions "
                "to get better results.**"
            )


            no_result_buttons = [
                [
                    InlineKeyboardButton(
                        "‼️ INSTRUCTIONS ‼️",
                        callback_data=(
                            "search_instructions"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "♻️ GOOGLE SEARCH ♻️",
                        url=google_search_url
                    )
                ]
            ]


            no_result_message = await client.send_message(
                chat_id=chat_id,
                text=no_result_text,
                reply_markup=InlineKeyboardMarkup(
                    no_result_buttons
                ),
                reply_to_message_id=reply_to_message_id
            )

            if no_result_message:
                asyncio.create_task(
                    auto_delete_message(
                        no_result_message,
                        delay_seconds=40
                    )
                )

            return


        # ====================================================
        # 9. SEARCH METRICS & IMDb DETAILS
        # ====================================================

        elapsed_sec = (
            f"{time.time() - start_time:.2f}"
        )

        total_files_count = len(results)

        user_name = (
            user.first_name or "User"
        )

        user_mention = (
            f'<a href="tg://user?id={user.id}">'
            f'<b>{html.escape(user_name)}</b>'
            f'</a>'
        )


        detected_audios = set()

        for f in results:

            langs = extract_file_languages(f)

            detected_audios.update(langs)


        priority_order = [
            "Telugu",
            "Tamil",
            "Hindi",
            "English",
            "Malayalam",
            "Kannada"
        ]


        sorted_audios = [
            l
            for l in priority_order
            if l in detected_audios
        ]


        for l in detected_audios:

            if l not in sorted_audios:
                sorted_audios.append(l)


        audio_str = (
            ", ".join(sorted_audios)
            if sorted_audios
            else "Multi"
        )


        target_lang = "te"

        for l in sorted_audios:

            if l in TMDB_LANG_MAP:

                target_lang = TMDB_LANG_MAP[l]

                break


        imdb_search_query = (
            locals().get("imdb_search_query")
            or base_movie_name
            .split("-")[0]
            .strip()
        )


        movie_details = (
            await get_imdb_movie_details(
                imdb_search_query,
                preferred_lang=target_lang
            )
        )


        landscape_banner_url = (
            movie_details.get("image")
            if movie_details
            else None
        )


        # ====================================================
        # 10. FINAL RESULT CAPTION
        # ====================================================

        caption_lines = []


        if (
            movie_details
            and movie_details.get("title")
        ):

            m_title = movie_details["title"]

            if (
                has_explicit_year
                and target_year
            ):
                m_title += (
                    f" - {target_year}"
                )

            elif movie_details.get("year"):

                m_title += (
                    f" - {movie_details['year']}"
                )

            caption_lines.append(
                f"🎬 <b>{html.escape(m_title)}</b>\n"
            )

        else:

            caption_lines.append(
                f"🎬 <b>"
                f"{html.escape(movie_name.title())}"
                f"</b>\n"
            )


        if movie_details:

            if (
                movie_details.get("rating")
                and movie_details["rating"] != "N/A"
            ):

                caption_lines.append(
                    "⭐ <b>RATING :</b> "
                    f"<code>{movie_details['rating']} / 10</code>"
                )


            if (
                movie_details.get("genres")
                and movie_details["genres"] != "N/A"
            ):

                caption_lines.append(
                    "🎭 <b>GENRE :</b> "
                    f"<code>{movie_details['genres']}</code>"
                )


            if (
                movie_details.get("runtime")
                and movie_details["runtime"] != "N/A"
            ):

                caption_lines.append(
                    "⏳ <b>RUN TIME :</b> "
                    f"<code>{movie_details['runtime']}</code>"
                )


        caption_lines.append(
            f"🔊 <b>AUDIO :</b> "
            f"<code>{audio_str}</code>\n"
        )


        caption_lines.extend([
            f"📁 <b>TOTAL FILES :</b> "
            f"<code>{total_files_count}</code>",

            f"📝 <b>REQUESTED BY :</b> "
            f"{user_mention}",

            f"⏰ <b>RESULT IN :</b> "
            f"<code>{elapsed_sec} s</code>\n",

            # =================================================
            # CHANGED TEXT
            # =================================================
            "🥦 <b><i>Requested Files</i></b> 👇"
        ])


        final_caption = "\n".join(
            caption_lines
        )


        # ====================================================
        # 11. SEARCH ID & CACHE
        # ====================================================

        search_id = str(
            uuid.uuid4()
        )

        menu_timestamp = int(
            datetime.now().timestamp()
        )


        cache_files = []

        for file in results:

            if "_id" in file:
                file["_id"] = str(
                    file["_id"]
                )

            cache_files.append(file)


        asyncio.create_task(
            save_search_cache(
                search_id,
                cache_files,
                movie_name
            )
        )


        asyncio.create_task(
            update_search_state(
                search_id,
                cache_files[:PAGE_LIMIT],
                "All",
                1
            )
        )


        # ====================================================
        # 12. BUILD FILE BUTTONS
        # ====================================================

        buttons = []

        for file in cache_files[:PAGE_LIMIT]:

            buttons.append(
                [
                    build_file_button(
                        file,
                        user_id,
                        menu_timestamp
                    )
                ]
            )


        # ====================================================
        # 13. LANGUAGE BUTTONS
        # ====================================================

        buttons.extend(
            language_buttons(
                search_id=search_id,
                timestamp=menu_timestamp,
                selected="All"
            )
        )


        # ====================================================
        # 14. SEND ALL
        # ====================================================

        buttons.append(
            [
                InlineKeyboardButton(
                    "📤 Send All",
                    callback_data=(
                        f"all:"
                        f"{user_id}:"
                        f"{search_id}:"
                        f"{menu_timestamp}"
                    )
                )
            ]
        )


        # ====================================================
        # 15. PAGINATION
        # ====================================================

        buttons.extend(
            pagination_buttons(
                search_id,
                1,
                len(cache_files),
                menu_timestamp
            )
        )


        reply_markup = InlineKeyboardMarkup(
            buttons
        )


        # ====================================================
        # 16. DISPATCH PHOTO BANNER
        # ====================================================

        sent_success = False
        sent_message = None


        if landscape_banner_url:

            try:

                sent_message = await client.send_photo(
                    chat_id=chat_id,
                    photo=landscape_banner_url,
                    caption=final_caption,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id
                )

                sent_success = True

            except Exception as pe:

                print(
                    "⚠️ Landscape direct URL failed "
                    f"({pe}), attempting stream...",
                    flush=True
                )

                try:

                    async with aiohttp.ClientSession() as session:

                        async with session.get(
                            landscape_banner_url,
                            timeout=aiohttp.ClientTimeout(
                                total=4
                            )
                        ) as img_resp:

                            if img_resp.status == 200:

                                img_bytes = (
                                    await img_resp.read()
                                )

                                sent_message = (
                                    await client.send_photo(
                                        chat_id=chat_id,
                                        photo=img_bytes,
                                        caption=final_caption,
                                        reply_markup=reply_markup,
                                        reply_to_message_id=reply_to_message_id
                                    )
                                )

                                sent_success = True

                except Exception as b_err:

                    print(
                        "⚠️ Stream fallback error: "
                        f"{b_err}",
                        flush=True
                    )


        # ====================================================
        # 17. TEXT FALLBACK
        # ====================================================

        if not sent_success:

            sent_message = await client.send_message(
                chat_id=chat_id,
                text=final_caption,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id
            )


        # ====================================================
        # 18. AUTO DELETE RESULT MENU
        # ====================================================

        if sent_message:

            asyncio.create_task(
                auto_delete_menu(
                    client=client,
                    chat_id=chat_id,
                    message_id=sent_message.id
                )
            )


        print(
            "✅ SEARCH RESULT SENT SUCCESSFULLY",
            flush=True
        )


    except Exception as e:

        print(
            f"❌ SEARCH ERROR : {e}",
            flush=True
        )

        try:

            await client.send_message(
                chat_id,
                "⚠ Something went wrong.",
                reply_to_message_id=reply_to_message_id
            )

        except Exception:
            pass


    finally:

        # ====================================================
        # DELETE LOADING MESSAGE
        # ====================================================

        if loading_msg:

            try:
                await loading_msg.delete()
            except Exception:
                pass


# ============================================================
# PRIVATE TEXT SEARCH HANDLER
# ============================================================

@app.on_message(
    filters.private
    & filters.text
    & ~filters.command([
        "start",
        "stats",
        "broadcast",
        "reindex",
        "reload",
        "ping",
        "usage",
        "owner",
        "delete",
        "generate_link",
        "imdb"
    ])
)
async def search_movie_handler(
    client,
    message: Message
):
    try:

        if not message.from_user:
            return

        if message.via_bot:
            return


        movie_name = (
            message.text or ""
        ).strip()


        # ====================================================
        # IGNORE BOT / FILE MESSAGES
        # ====================================================

        if (
            "Size :-" in movie_name
            or "Size:" in movie_name
            or "@CinemaVetaBot" in movie_name
            or "@mrDuDeHoLic" in movie_name
            or movie_name.startswith("📁")
            or "Results -" in movie_name
        ):
            return


        # ====================================================
        # @BOTNAME SEARCH
        # ====================================================

        if movie_name.startswith("@"):

            parts = movie_name.split()

            movie_name = " ".join(
                parts[1:]
            )


        # ====================================================
        # /SEARCH COMMAND
        # ====================================================

        if movie_name.lower().startswith(
            "/search"
        ):

            movie_name = (
                movie_name[7:]
                .strip()
            )


        if not movie_name:
            return


        # ====================================================
        # FORCE SUBSCRIBE
        # ====================================================

        if not await enforce_fsub(
            client,
            message,
            payload=movie_name
        ):
            return


        # ====================================================
        # EXECUTE SEARCH
        # ====================================================

        await execute_search(
            client=client,
            user=message.from_user,
            chat_id=message.chat.id,
            movie_name=movie_name,
            reply_to_message_id=message.id,
            allow_spelling_suggestions=True
        )


    except Exception as e:

        print(
            f"❌ SEARCH HANDLER ERROR : {e}",
            flush=True
        )

        try:

            await message.reply_text(
                "⚠️ Something went wrong.",
                quote=True
            )

        except Exception:
            pass
