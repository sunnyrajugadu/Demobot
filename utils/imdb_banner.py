import io
import re

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ============================================================
# IMDb Custom Banner Generator
# File: utils/imdb_banner.py
#
# Usage from handlers/imdb.py:
#     from utils.imdb_banner import create_imdb_banner
#
#     banner = await create_imdb_banner(info, bot_user)
#
# "info" should contain:
#     id, title, year, rating, runtime, certificate,
#     genres, storyline, poster
# ============================================================

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"

# Existing TMDB key used by the bot.
TMDB_KEY = "7f43669a428c09611a0518fa9c0bbddb"

HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=15,
    connect=6,
    sock_read=12,
)

IMDB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
)

BANNER_WIDTH = 1536
BANNER_HEIGHT = 864

# Left-side branding shown in the reference image.
BANNER_CHANNEL = "@NXT_HUB"


# ============================================================
# Basic helpers
# ============================================================

def clean_text(value, default="N/A"):
    if value is None:
        return default

    if isinstance(value, str):
        value = value.strip()
    else:
        value = str(value).strip()

    return value if value else default


def unique_strings(values):
    result = []
    seen = set()

    for value in values or []:
        if isinstance(value, dict):
            value = (
                value.get("text")
                or value.get("name")
                or value.get("value")
            )

        value = clean_text(value, "")
        if not value:
            continue

        key = value.casefold()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def normalize_certificate(value):
    value = clean_text(value, "")

    if not value:
        return ""

    normalized = value.strip().upper()

    aliases = {
        "UA": "U/A",
        "U.A.": "U/A",
        "U A": "U/A",
        "U/A": "U/A",
    }

    return aliases.get(normalized, value.strip())


# ============================================================
# Font handling
# ============================================================

def _find_font(size, bold=False):
    """
    Try common Linux/Render fonts first.
    Falls back to Pillow's bundled/default font.
    """

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue

    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _font(size, bold=False):
    return _find_font(size, bold)


# ============================================================
# Image helpers
# ============================================================

def _cover_image(image, size):
    """Resize/crop image to completely fill size without distortion."""

    image = image.convert("RGB")

    src_w, src_h = image.size
    dst_w, dst_h = size

    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", size, (25, 25, 25))

    src_ratio = src_w / src_h
    dst_ratio = dst_w / dst_h

    if src_ratio > dst_ratio:
        new_h = dst_h
        new_w = max(1, int(new_h * src_ratio))
    else:
        new_w = dst_w
        new_h = max(1, int(new_w / src_ratio))

    image = image.resize(
        (new_w, new_h),
        Image.Resampling.LANCZOS,
    )

    left = max(0, (new_w - dst_w) // 2)
    top = max(0, (new_h - dst_h) // 2)

    return image.crop(
        (
            left,
            top,
            left + dst_w,
            top + dst_h,
        )
    )


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)

    ImageDraw.Draw(mask).rounded_rectangle(
        (
            0,
            0,
            size[0] - 1,
            size[1] - 1,
        ),
        radius=radius,
        fill=255,
    )

    return mask


def _fit_text(draw, text, font, max_width):
    """Shorten a single line until it fits."""

    text = str(text or "").strip()

    if not text:
        return ""

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    if bbox[2] - bbox[0] <= max_width:
        return text

    suffix = "..."

    while text:
        candidate = text.rstrip() + suffix

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        if bbox[2] - bbox[0] <= max_width:
            return candidate

        text = text[:-1]

    return suffix


def _wrap_text(draw, text, font, max_width, max_lines=4):
    """
    Wrap text into readable lines while keeping the banner compact.
    """

    text = re.sub(r"\s+", " ", str(text or "").strip())

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

            if len(lines) >= max_lines:
                break

    if current and len(lines) < max_lines:
        lines.append(current)

    # If text was cut, append an ellipsis to the final line.
    if len(lines) >= max_lines:
        joined = " ".join(lines)

        if len(joined) < len(text):
            last = lines[-1]

            fitted = _fit_text(
                draw,
                last,
                font,
                max_width - 30,
            )

            lines[-1] = fitted.rstrip(".") + "..."

    return lines[:max_lines]


def _draw_pill(
    base,
    xy,
    text,
    font,
    fill=(255, 255, 255, 42),
    outline=(255, 255, 255, 105),
    text_fill=(255, 255, 255, 255),
    padding_x=18,
    padding_y=9,
    radius=22,
):
    draw = ImageDraw.Draw(base, "RGBA")

    x, y = xy

    text = str(text or "")

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    rect = (
        x,
        y,
        x + tw + padding_x * 2,
        y + th + padding_y * 2,
    )

    draw.rounded_rectangle(
        rect,
        radius=radius,
        fill=fill,
        outline=outline,
        width=1,
    )

    draw.text(
        (
            x + padding_x,
            y + padding_y - bbox[1],
        ),
        text,
        font=font,
        fill=text_fill,
    )

    return rect


# ============================================================
# TMDB lookup
# ============================================================

async def fetch_tmdb_backdrop_and_poster(
    imdb_id,
    title=None,
    year=None,
):
    """
    Resolve IMDb ID through TMDB.

    Returns:
        (backdrop_url, poster_url)
    """

    if not imdb_id:
        return None, None

    headers = {
        "User-Agent": IMDB_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession(
            timeout=HTTP_TIMEOUT,
            headers=headers,
        ) as session:

            find_url = f"{TMDB_API_URL}/find/{imdb_id}"

            async with session.get(
                find_url,
                params={
                    "api_key": TMDB_KEY,
                    "external_source": "imdb_id",
                },
            ) as response:

                if response.status != 200:
                    return None, None

                found = await response.json(
                    content_type=None
                )

            results = (
                found.get("movie_results")
                or found.get("tv_results")
                or []
            )

            if not results:
                return None, None

            target_title = str(
                title or ""
            ).strip().casefold()

            target_year = str(
                year or ""
            ).strip()

            selected = None

            # First try exact title + year.
            for item in results:
                item_title = str(
                    item.get("title")
                    or item.get("name")
                    or item.get("original_title")
                    or item.get("original_name")
                    or ""
                ).strip()

                release = str(
                    item.get("release_date")
                    or item.get("first_air_date")
                    or ""
                )

                item_year = release[:4]

                if (
                    target_title
                    and item_title.casefold() == target_title
                    and (
                        not target_year
                        or item_year == target_year
                    )
                ):
                    selected = item
                    break

            # Then exact title without year.
            if selected is None and target_title:
                for item in results:
                    item_title = str(
                        item.get("title")
                        or item.get("name")
                        or item.get("original_title")
                        or item.get("original_name")
                        or ""
                    ).strip()

                    if item_title.casefold() == target_title:
                        selected = item
                        break

            selected = selected or results[0]

            backdrop_path = selected.get(
                "backdrop_path"
            )

            poster_path = selected.get(
                "poster_path"
            )

            backdrop_url = (
                f"{TMDB_IMAGE_BASE}w1280{backdrop_path}"
                if backdrop_path
                else None
            )

            poster_url = (
                f"{TMDB_IMAGE_BASE}w780{poster_path}"
                if poster_path
                else None
            )

            return backdrop_url, poster_url

    except Exception as exc:
        print(
            f"TMDB Banner Image Lookup Error "
            f"[{imdb_id}]: {exc}",
            flush=True,
        )

        return None, None


# ============================================================
# Download remote image
# ============================================================

async def _download_image(url):
    if not url:
        return None

    try:
        async with aiohttp.ClientSession(
            timeout=HTTP_TIMEOUT,
            headers={
                "User-Agent": IMDB_USER_AGENT,
            },
        ) as session:

            async with session.get(url) as response:

                if response.status != 200:
                    return None

                raw = await response.read()

        image = Image.open(
            io.BytesIO(raw)
        ).convert("RGB")

        return image

    except Exception as exc:
        print(
            f"IMDb Banner Image Download Error: {exc}",
            flush=True,
        )

        return None


# ============================================================
# Main banner generator
# ============================================================

async def create_imdb_banner(
    info,
    bot_username="CinemaVetaBot",
):
    """
    Generate the custom IMDb banner.

    Returns:
        io.BytesIO

    The returned object can directly be used by Pyrogram:

        await client.send_photo(
            chat_id=...,
            photo=banner,
        )
    """

    info = info or {}

    imdb_id = info.get("id")
    title = clean_text(
        info.get("title"),
        "Unknown Title",
    )

    year = clean_text(
        info.get("year"),
        "N/A",
    )

    rating = clean_text(
        info.get("rating"),
        "N/A",
    )

    runtime = clean_text(
        info.get("runtime"),
        "N/A",
    )

    storyline = clean_text(
        info.get("storyline"),
        "No storyline available.",
    )

    certificate = (
        normalize_certificate(
            info.get("certificate")
        )
        or "Not Rated"
    )

    genres = unique_strings(
        info.get("genres") or []
    )

    # --------------------------------------------------------
    # Fetch TMDB backdrop + poster
    # --------------------------------------------------------

    backdrop_url, tmdb_poster_url = (
        await fetch_tmdb_backdrop_and_poster(
            imdb_id,
            title,
            year,
        )
    )

    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    background = await _download_image(
        backdrop_url
    )

    # If TMDB backdrop isn't available,
    # use IMDb poster as a background.
    if background is None:
        background = await _download_image(
            info.get("poster")
        )

    # Final solid fallback.
    if background is None:
        background = Image.new(
            "RGB",
            (
                BANNER_WIDTH,
                BANNER_HEIGHT,
            ),
            (25, 25, 25),
        )

    background = _cover_image(
        background,
        (
            BANNER_WIDTH,
            BANNER_HEIGHT,
        ),
    )

    # Cinematic slight blur.
    background = background.filter(
        ImageFilter.GaussianBlur(
            radius=1.8
        )
    )

    canvas = background.convert("RGBA")

    # --------------------------------------------------------
    # Cinematic dark overlay
    # --------------------------------------------------------

    overlay = Image.new(
        "RGBA",
        canvas.size,
        (0, 0, 0, 0),
    )

    od = ImageDraw.Draw(
        overlay,
        "RGBA",
    )

    for x in range(BANNER_WIDTH):

        ratio = x / max(
            BANNER_WIDTH - 1,
            1,
        )

        alpha = int(
            185 - (ratio * 82)
        )

        od.line(
            (
                x,
                0,
                x,
                BANNER_HEIGHT,
            ),
            fill=(
                0,
                0,
                0,
                max(80, alpha),
            ),
        )

    # Additional overall dark layer.
    od.rectangle(
        (
            0,
            0,
            BANNER_WIDTH,
            BANNER_HEIGHT,
        ),
        fill=(0, 0, 0, 35),
    )

    canvas = Image.alpha_composite(
        canvas,
        overlay,
    )

    draw = ImageDraw.Draw(
        canvas,
        "RGBA",
    )

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------

    title_font = _font(
        64,
        True,
    )

    rating_font = _font(
        30,
        True,
    )

    body_font = _font(
        24,
        False,
    )

    body_bold = _font(
        25,
        True,
    )

    pill_font = _font(
        22,
        True,
    )

    small_font = _font(
        19,
        True,
    )

    brand_font = _font(
        26,
        True,
    )

    # --------------------------------------------------------
    # Main layout
    # --------------------------------------------------------

    left_x = 68

    text_right = 1040

    max_text_width = (
        text_right - left_x
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title_text = _fit_text(
        draw,
        title.upper(),
        title_font,
        max_text_width - 220,
    )

    title_y = 205

    # Shadow.
    draw.text(
        (
            left_x + 4,
            title_y + 5,
        ),
        title_text,
        font=title_font,
        fill=(0, 0, 0, 180),
    )

    # Main white title.
    draw.text(
        (
            left_x,
            title_y,
        ),
        title_text,
        font=title_font,
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # IMDb rating
    # --------------------------------------------------------

    title_bbox = draw.textbbox(
        (
            0,
            0,
        ),
        title_text,
        font=title_font,
    )

    title_width = (
        title_bbox[2] - title_bbox[0]
    )

    rating_x = left_x + min(
        title_width + 24,
        max_text_width - 190,
    )

    # Star.
    draw.text(
        (
            rating_x,
            title_y + 15,
        ),
        "★",
        font=_font(
            30,
            True,
        ),
        fill=(255, 193, 61, 255),
    )

    # Rating number.
    draw.text(
        (
            rating_x + 33,
            title_y + 16,
        ),
        rating,
        font=rating_font,
        fill=(255, 255, 255, 255),
    )

    # IMDb badge.
    imdb_box_x = (
        rating_x + 105
    )

    draw.rounded_rectangle(
        (
            imdb_box_x,
            title_y + 12,
            imdb_box_x + 78,
            title_y + 52,
        ),
        radius=10,
        fill=(245, 190, 35, 235),
    )

    draw.text(
        (
            imdb_box_x + 11,
            title_y + 18,
        ),
        "IMDb",
        font=small_font,
        fill=(0, 0, 0, 255),
    )

    # --------------------------------------------------------
    # Title underline
    # --------------------------------------------------------

    underline_w = min(
        165,
        max(
            95,
            title_width,
        ),
    )

    draw.rounded_rectangle(
        (
            left_x,
            title_bbox[3] + 6,
            left_x + underline_w,
            title_bbox[3] + 11,
        ),
        radius=3,
        fill=(205, 147, 82, 255),
    )

    # --------------------------------------------------------
    # Storyline
    # --------------------------------------------------------

    story_lines = _wrap_text(
        draw,
        storyline,
        body_bold,
        max_text_width,
        max_lines=4,
    )

    story_y = 330

    for index, line in enumerate(
        story_lines
    ):
        draw.text(
            (
                left_x + 2,
                story_y + index * 43,
            ),
            line,
            font=body_bold,
            fill=(255, 255, 255, 245),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 125),
        )

    # --------------------------------------------------------
    # Information pills
    # --------------------------------------------------------

    pill_y = 510
    pill_x = left_x

    # Certificate
    rect = _draw_pill(
        canvas,
        (
            pill_x,
            pill_y,
        ),
        certificate,
        pill_font,
        fill=(35, 35, 35, 175),
        outline=(255, 255, 255, 100),
        text_fill=(255, 255, 255, 255),
        padding_x=18,
        padding_y=8,
        radius=20,
    )

    pill_x = rect[2] + 12

    # Tomato-style popularity indicator.
    # Uses text instead of an external icon dependency.
    rating_value = (
        f"🍅 {rating}"
        if rating != "N/A"
        else "🍅 N/A"
    )

    rect = _draw_pill(
        canvas,
        (
            pill_x,
            pill_y,
        ),
        rating_value,
        pill_font,
        fill=(255, 255, 255, 185),
        outline=(255, 255, 255, 100),
        text_fill=(35, 35, 35, 255),
        padding_x=17,
        padding_y=8,
        radius=20,
    )

    pill_x = rect[2] + 12

    # Runtime
    rect = _draw_pill(
        canvas,
        (
            pill_x,
            pill_y,
        ),
        runtime,
        pill_font,
        fill=(255, 255, 255, 80),
        outline=(255, 255, 255, 100),
        text_fill=(255, 255, 255, 255),
        padding_x=18,
        padding_y=8,
        radius=20,
    )

    pill_x = rect[2] + 12

    # Genres
    for genre in genres[:2]:
        rect = _draw_pill(
            canvas,
            (
                pill_x,
                pill_y,
            ),
            genre.upper(),
            pill_font,
            fill=(255, 255, 255, 80),
            outline=(255, 255, 255, 100),
            text_fill=(255, 255, 255, 255),
            padding_x=17,
            padding_y=8,
            radius=20,
        )

        pill_x = rect[2] + 12

    # Year
    _draw_pill(
        canvas,
        (
            pill_x,
            pill_y,
        ),
        year,
        pill_font,
        fill=(255, 255, 255, 180),
        outline=(255, 255, 255, 100),
        text_fill=(30, 30, 30, 255),
        padding_x=20,
        padding_y=8,
        radius=20,
    )

    # --------------------------------------------------------
    # Telegram channel badge
    # --------------------------------------------------------

    source_y = 610

    _draw_pill(
        canvas,
        (
            left_x,
            source_y,
        ),
        BANNER_CHANNEL,
        brand_font,
        fill=(60, 60, 60, 155),
        outline=(255, 255, 255, 110),
        text_fill=(255, 255, 255, 255),
        padding_x=28,
        padding_y=11,
        radius=34,
    )

    # --------------------------------------------------------
    # Poster card
    # --------------------------------------------------------

    poster = None

    if tmdb_poster_url:
        poster = await _download_image(
            tmdb_poster_url
        )

    if poster is None:
        poster = await _download_image(
            info.get("poster")
        )

    poster_box = (
        1125,
        160,
        1482,
        704,
    )

    px1, py1, px2, py2 = poster_box

    card_w = px2 - px1
    card_h = py2 - py1

    # Shadow layer.
    shadow = Image.new(
        "RGBA",
        canvas.size,
        (0, 0, 0, 0),
    )

    sd = ImageDraw.Draw(
        shadow,
        "RGBA",
    )

    sd.rounded_rectangle(
        (
            px1 + 10,
            py1 + 14,
            px2 + 10,
            py2 + 14,
        ),
        radius=22,
        fill=(0, 0, 0, 145),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            12
        )
    )

    canvas = Image.alpha_composite(
        canvas,
        shadow,
    )

    draw = ImageDraw.Draw(
        canvas,
        "RGBA",
    )

    # Poster.
    if poster is not None:

        inner_w = card_w - 14
        inner_h = card_h - 14

        poster = _cover_image(
            poster,
            (
                inner_w,
                inner_h,
            ),
        )

        mask = _rounded_mask(
            (
                inner_w,
                inner_h,
            ),
            17,
        )

        poster_rgba = poster.convert(
            "RGBA"
        )

        poster_rgba.putalpha(
            mask
        )

        canvas.alpha_composite(
            poster_rgba,
            (
                px1 + 7,
                py1 + 7,
            ),
        )

    # White poster border.
    draw = ImageDraw.Draw(
        canvas,
        "RGBA",
    )

    draw.rounded_rectangle(
        poster_box,
        radius=23,
        outline=(255, 255, 255, 245),
        width=7,
    )

    # --------------------------------------------------------
    # Bottom-right bot branding
    # --------------------------------------------------------

    bot_label = (
        "@"
        + str(
            bot_username
            or "CinemaVetaBot"
        ).lstrip("@")
    )

    bot_font = _font(
        28,
        True,
    )

    bbox = draw.textbbox(
        (
            0,
            0,
        ),
        bot_label,
        font=bot_font,
    )

    bw = (
        bbox[2]
        - bbox[0]
        + 46
    )

    bh = (
        bbox[3]
        - bbox[1]
        + 24
    )

    bx = (
        BANNER_WIDTH
        - bw
        - 70
    )

    by = (
        BANNER_HEIGHT
        - bh
        - 38
    )

    draw.rounded_rectangle(
        (
            bx,
            by,
            bx + bw,
            by + bh,
        ),
        radius=30,
        fill=(55, 55, 55, 170),
        outline=(255, 255, 255, 90),
        width=1,
    )

    draw.text(
        (
            bx + 23,
            by + 12,
        ),
        bot_label,
        font=bot_font,
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # Export JPEG
    # --------------------------------------------------------

    output = io.BytesIO()

    canvas.convert("RGB").save(
        output,
        format="JPEG",
        quality=94,
        optimize=True,
    )

    output.seek(0)

    output.name = "imdb_banner.jpg"

    return output
