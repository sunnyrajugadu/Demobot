import io
import re

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"
TMDB_KEY = "7f43669a428c09611a0518fa9c0bbddb"

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=6, sock_read=12)

IMDB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
)

BANNER_WIDTH = 1536
BANNER_HEIGHT = 864
BANNER_CHANNEL = "@NXT_HUB"


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
            value = value.get("text") or value.get("name") or value.get("value")
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
    aliases = {"UA": "U/A", "U.A.": "U/A", "U A": "U/A", "U/A": "U/A"}
    return aliases.get(normalized, value.strip())


def _find_font(size, bold=False):
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


def _cover_image(image, size):
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

    image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - dst_w) // 2)
    top = max(0, (new_h - dst_h) // 2)
    return image.crop((left, top, left + dst_w, top + dst_h))


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _fit_text(draw, text, font, max_width):
    text = str(text or "").strip()
    if not text:
        return ""
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text
    suffix = "..."
    while text:
        candidate = text.rstrip() + suffix
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
        text = text[:-1]
    return suffix


def _wrap_text(draw, text, font, max_width, max_lines=4):
    text = re.sub(r"\s+", " ", str(text or "").strip())
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines]


def _draw_pill(base, xy, text, font, fill=(255, 255, 255, 42), outline=(255, 255, 255, 105), text_fill=(255, 255, 255, 255), padding_x=18, padding_y=9, radius=22):
    draw = ImageDraw.Draw(base, "RGBA")
    x, y = xy
    text = str(text or "")
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    rect = (x, y, x + tw + padding_x * 2, y + th + padding_y * 2)
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=1)
    draw.text((x + padding_x, y + padding_y - bbox[1]), text, font=font, fill=text_fill)
    return rect


async def fetch_tmdb_backdrop_and_poster(imdb_id, title=None, year=None):
    if not imdb_id:
        return None, None
    headers = {"User-Agent": IMDB_USER_AGENT, "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=headers) as session:
            find_url = f"{TMDB_API_URL}/find/{imdb_id}"
            async with session.get(find_url, params={"api_key": TMDB_KEY, "external_source": "imdb_id"}) as response:
                if response.status != 200:
                    return None, None
                found = await response.json(content_type=None)
            results = found.get("movie_results") or found.get("tv_results") or []
            if not results:
                return None, None
            selected = results[0]
            backdrop_path = selected.get("backdrop_path")
            poster_path = selected.get("poster_path")
            return (
                f"{TMDB_IMAGE_BASE}w1280{backdrop_path}" if backdrop_path else None,
                f"{TMDB_IMAGE_BASE}w780{poster_path}" if poster_path else None,
            )
    except Exception:
        return None, None


async def _download_image(url):
    if not url:
        return None
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers={"User-Agent": IMDB_USER_AGENT}) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                raw = await response.read()
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None


async def create_imdb_banner(info, bot_username="CinemaVetaBot"):
    info = info or {}
    imdb_id = info.get("id")
    title = clean_text(info.get("title"), "Unknown Title")
    year = clean_text(info.get("year"), "N/A")
    rating = clean_text(info.get("rating"), "N/A")
    runtime = clean_text(info.get("runtime"), "N/A")
    storyline = clean_text(info.get("storyline"), "No storyline available.")
    certificate = normalize_certificate(info.get("certificate")) or "Not Rated"
    genres = unique_strings(info.get("genres") or [])

    backdrop_url, tmdb_poster_url = await fetch_tmdb_backdrop_and_poster(imdb_id, title, year)

    background = await _download_image(backdrop_url)
    if background is None:
        background = await _download_image(info.get("poster"))
    if background is None:
        background = Image.new("RGB", (BANNER_WIDTH, BANNER_HEIGHT), (25, 25, 25))

    background = _cover_image(background, (BANNER_WIDTH, BANNER_HEIGHT))
    background = background.filter(ImageFilter.GaussianBlur(radius=1.8))
    canvas = background.convert("RGBA")

    # Opacity & Overlay configuration aligned with 1st image reference
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")
    for x in range(BANNER_WIDTH):
        ratio = x / max(BANNER_WIDTH - 1, 1)
        alpha = int(185 - (ratio * 82))
        od.line((x, 0, x, BANNER_HEIGHT), fill=(0, 0, 0, max(80, alpha)))
    od.rectangle((0, 0, BANNER_WIDTH, BANNER_HEIGHT), fill=(0, 0, 0, 35))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas, "RGBA")

    title_font = _font(64, True)
    rating_font = _font(30, True)
    body_bold = _font(25, True)
    pill_font = _font(22, True)
    small_font = _font(19, True)
    brand_font = _font(26, True)

    left_x = 68
    text_right = 1040
    max_text_width = text_right - left_x

    title_text = _fit_text(draw, title.upper(), title_font, max_text_width - 220)
    title_y = 205

    draw.text((left_x + 4, title_y + 5), title_text, font=title_font, fill=(0, 0, 0, 180))
    draw.text((left_x, title_y), title_text, font=title_font, fill=(255, 255, 255, 255))

    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    rating_x = left_x + min(title_width + 24, max_text_width - 190)

    draw.text((rating_x, title_y + 15), "★", font=_font(30, True), fill=(255, 193, 61, 255))
    draw.text((rating_x + 33, title_y + 16), rating, font=rating_font, fill=(255, 255, 255, 255))

    imdb_box_x = rating_x + 105
    draw.rounded_rectangle((imdb_box_x, title_y + 12, imdb_box_x + 78, title_y + 52), radius=10, fill=(245, 190, 35, 235))
    draw.text((imdb_box_x + 11, title_y + 18), "IMDb", font=small_font, fill=(0, 0, 0, 255))

    underline_w = min(165, max(95, title_width))
    draw.rounded_rectangle((left_x, title_bbox[3] + 6, left_x + underline_w, title_bbox[3] + 11), radius=3, fill=(205, 147, 82, 255))

    story_lines = _wrap_text(draw, storyline, body_bold, max_text_width, max_lines=4)
    story_y = 330
    for index, line in enumerate(story_lines):
        draw.text((left_x + 2, story_y + index * 43), line, font=body_bold, fill=(255, 255, 255, 245), stroke_width=1, stroke_fill=(0, 0, 0, 125))

    # Fixed pills renderer to avoid blank white boxes completely (unlike 2nd image)
    pill_y = 510
    pill_x = left_x

    rect = _draw_pill(canvas, (pill_x, pill_y), certificate, pill_font, fill=(35, 35, 35, 175), outline=(255, 255, 255, 100), text_fill=(255, 255, 255, 255), radius=20)
    pill_x = rect[2] + 12

    tomato_val = f"🍅 {rating}" if rating != "N/A" else "🍅 N/A"
    rect = _draw_pill(canvas, (pill_x, pill_y), tomato_val, pill_font, fill=(255, 255, 255, 185), outline=(255, 255, 255, 100), text_fill=(35, 35, 35, 255), radius=20)
    pill_x = rect[2] + 12

    rect = _draw_pill(canvas, (pill_x, pill_y), runtime, pill_font, fill=(255, 255, 255, 80), outline=(255, 255, 255, 100), text_fill=(255, 255, 255, 255), radius=20)
    pill_x = rect[2] + 12

    pill_items = [genre.upper() for genre in genres[:2]]
    pill_items.append(year)
    pills_right = 1035

    for item_index, item in enumerate(pill_items):
        item_text = str(item or "").strip()
        if not item_text or pill_x >= pills_right:
            break
        bbox = draw.textbbox((0, 0), item_text, font=pill_font)
        text_width = bbox[2] - bbox[0]
        padding_x = 20 if item_index == len(pill_items) - 1 else 17
        pill_width = text_width + (padding_x * 2)

        if pill_x + pill_width > pills_right:
            break

        rect = _draw_pill(
            canvas,
            (pill_x, pill_y),
            item_text,
            pill_font,
            fill=(255, 255, 255, 180) if item_index == len(pill_items) - 1 else (255, 255, 255, 80),
            outline=(255, 255, 255, 100),
            text_fill=(30, 30, 30, 255) if item_index == len(pill_items) - 1 else (255, 255, 255, 255),
            padding_x=padding_x,
            padding_y=8,
            radius=20,
        )
        pill_x = rect[2] + 12

    # Left-side brand tag (@NXT_HUB)
    _draw_pill(canvas, (left_x, 610), BANNER_CHANNEL, brand_font, fill=(60, 60, 60, 155), outline=(255, 255, 255, 110), text_fill=(255, 255, 255, 255), padding_x=28, padding_y=11, radius=34)

    # Poster card section
    poster = None
    if tmdb_poster_url:
        poster = await _download_image(tmdb_poster_url)
    if poster is None:
        poster = await _download_image(info.get("poster"))

    px1, py1, px2, py2 = (1125, 160, 1482, 704)
    card_w = px2 - px1
    card_h = py2 - py1

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")
    sd.rounded_rectangle((px1 + 10, py1 + 14, px2 + 10, py2 + 14), radius=22, fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas = Image.alpha_composite(canvas, shadow)

    draw = ImageDraw.Draw(canvas, "RGBA")

    if poster is not None:
        inner_w = card_w - 14
        inner_h = card_h - 14
        poster = _cover_image(poster, (inner_w, inner_h))
        mask = _rounded_mask((inner_w, inner_h), 17)
        poster_rgba = poster.convert("RGBA")
        poster_rgba.putalpha(mask)
        canvas.alpha_composite(poster_rgba, (px1 + 7, py1 + 7))

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((px1, py1, px2, py2), radius=23, outline=(255, 255, 255, 245), width=7)

    # Single bottom-right bot branding watermark (Duplicate @NXT_HUB removed completely)
    bot_label = "@" + str(bot_username or "CinemaVetaBot").lstrip("@")
    bot_font = _font(28, True)
    bbox = draw.textbbox((0, 0), bot_label, font=bot_font)
    bw = bbox[2] - bbox[0] + 46
    bh = bbox[3] - bbox[1] + 24
    bx = BANNER_WIDTH - bw - 70
    by = BANNER_HEIGHT - bh - 38

    draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=30, fill=(55, 55, 55, 170), outline=(255, 255, 255, 90), width=1)
    draw.text((bx + 23, by + 12), bot_label, font=bot_font, fill=(255, 255, 255, 255))

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=94, optimize=True)
    output.seek(0)
    output.name = "imdb_banner.jpg"
    return output
