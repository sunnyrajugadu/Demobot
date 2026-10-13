import io
import re

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ============================================================
# IMDb Custom Banner Generator (Original Ultra-HD Quality & High-Speed)
# File: utils/imdb_banner.py
# ============================================================

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"
TMDB_KEY = "7f43669a428c09611a0518fa9c0bbddb"

HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=15,
    connect=4,
    sock_read=10,
)

IMDB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
)

BANNER_WIDTH = 1536
BANNER_HEIGHT = 864


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
            value = value.get("text") or value.get("name") or value.get("value")
        value = clean_text(value, "")
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def format_runtime_short(runtime_str):
    """Runtime ni '1 hrs 56 mins' nunchi 2nd image lo unna '1H 56M' format ki convert chesthundi"""
    if not runtime_str or runtime_str == "N/A":
        return "N/A"
    
    clean = str(runtime_str).upper()
    
    if re.search(r"\d+H\s*\d*M*", clean):
        return re.sub(r"\s+", " ", clean).strip()
    
    hours_match = re.search(r"(\d+)\s*(?:HRS?|HOURS?|H)", clean)
    mins_match = re.search(r"(\d+)\s*(?:MINS?|MINUTES?|M)", clean)
    
    h = hours_match.group(1) if hours_match else None
    m = mins_match.group(1) if mins_match else None
    
    if h and m:
        return f"{h}H {m}M"
    if h:
        return f"{h}H"
    if m:
        return f"{m}M"
        
    return clean


# ============================================================
# Font handling
# ============================================================

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


# ============================================================
# Image helpers & Poster Multi-Color Extraction
# ============================================================

def _get_poster_color_palette(image, count=4):
    """Poster nunchi multi-color distinct shades palette ni auto-detect chesthundi."""
    default_palette = [
        (205, 155, 115),  # Light Tan (Runtime) -> Dark text
        (168, 105, 68),   # Warm Terracotta (Genre 1) -> White text
        (185, 128, 86),   # Medium Sand (Genre 2) -> White text
        (130, 95, 78),    # Deep Slate/Brown (Year) -> White text
    ]
    if not image:
        return default_palette
    try:
        small = image.convert("RGB").resize((90, 90), Image.Resampling.BILINEAR)
        palette = small.quantize(colors=20)
        color_counts = palette.getcolors()
        if not color_counts:
            return default_palette

        palette_colors = palette.getpalette()[:60]  # 20 * 3
        extracted = []

        for freq, idx in sorted(color_counts, key=lambda x: x[0], reverse=True):
            r = palette_colors[idx * 3]
            g = palette_colors[idx * 3 + 1]
            b = palette_colors[idx * 3 + 2]

            lum = 0.299 * r + 0.587 * g + 0.114 * b
            sat = max(r, g, b) - min(r, g, b)

            if 50 < lum < 220 and sat > 15:
                is_unique = True
                for (er, eg, eb) in extracted:
                    dist = abs(r - er) + abs(g - eg) + abs(b - eb)
                    if dist < 38:
                        is_unique = False
                        break
                if is_unique:
                    extracted.append((r, g, b))
                if len(extracted) >= count:
                    break

        if extracted:
            base_r, base_g, base_b = extracted[0]
            while len(extracted) < count:
                factor = 0.82 ** len(extracted)
                extracted.append((
                    max(50, int(base_r * factor)),
                    max(40, int(base_g * factor)),
                    max(35, int(base_g * factor)),
                ))
            return extracted
    except Exception:
        pass
    return default_palette


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

    if len(lines) >= max_lines:
        joined = " ".join(lines)
        if len(joined) < len(text):
            last = lines[-1]
            fitted = _fit_text(draw, last, font, max_width - 30)
            lines[-1] = fitted.rstrip(".") + "..."

    return lines[:max_lines]


def _draw_pill(
    base,
    xy,
    text,
    font,
    fill=(175, 126, 94, 255),
    padding_x=20,
    padding_y=10,
    radius=22,
):
    """Pill color luminance batti light colors ki Black text, dark colors ki White text auto select chesthundhi"""
    draw = ImageDraw.Draw(base, "RGBA")
    x, y = xy
    text = str(text or "")

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    rect = (
        x,
        y,
        x + tw + padding_x * 2,
        y + th + padding_y * 2,
    )

    draw.rounded_rectangle(rect, radius=radius, fill=fill)

    text_x = x + padding_x
    text_y = y + padding_y - bbox[1]

    r, g, b = fill[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b

    if luminance > 165:
        text_fill = (22, 22, 22, 240)
        shadow_fill = (255, 255, 255, 70)
        draw.text((text_x + 1, text_y + 1), text, font=font, fill=shadow_fill)
    else:
        text_fill = (255, 255, 255, 255)
        shadow_fill = (0, 0, 0, 160)
        draw.text((text_x + 1, text_y + 1), text, font=font, fill=shadow_fill)

    draw.text((text_x, text_y), text, font=font, fill=text_fill)

    return rect


def _draw_telegram_badge(canvas, xy, username, font):
    """Frosted Glass (Transparent + Blurred) Telegram pill"""
    x, y = xy
    
    text = str(username).strip()
    if not text.startswith("@"):
        text = f"@{text}"

    temp_draw = ImageDraw.Draw(canvas)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pill_h = 54
    icon_size = 40
    padding_left = 10
    spacing = 14
    padding_right = 26
    pill_w = padding_left + icon_size + spacing + tw + padding_right
    box_rect = (x, y, x + pill_w, y + pill_h)

    crop_x1 = max(0, x - 12)
    crop_y1 = max(0, y - 12)
    crop_x2 = min(canvas.width, x + pill_w + 12)
    crop_y2 = min(canvas.height, y + pill_h + 12)

    cropped = canvas.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    blurred = cropped.filter(ImageFilter.BoxBlur(8))

    mask = Image.new("L", (pill_w, pill_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pill_w, pill_h), radius=pill_h // 2, fill=255)

    offset_x = x - crop_x1
    offset_y = y - crop_y1
    patch = blurred.crop((offset_x, offset_y, offset_x + pill_w, offset_y + pill_h))
    canvas.paste(patch, (x, y), mask)

    glass_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glass_overlay, "RGBA")
    gd.rounded_rectangle(
        box_rect,
        radius=pill_h // 2,
        fill=(255, 255, 255, 38),
        outline=(255, 255, 255, 75),
        width=1,
    )
    canvas.alpha_composite(glass_overlay)

    draw = ImageDraw.Draw(canvas, "RGBA")

    icon_x = x + padding_left
    icon_y = y + (pill_h - icon_size) // 2
    draw.ellipse(
        (icon_x, icon_y, icon_x + icon_size, icon_y + icon_size),
        fill=(42, 171, 238, 255),
    )

    cx = icon_x + icon_size / 2
    cy = icon_y + icon_size / 2
    points = [
        (cx - 9, cy - 1),
        (cx + 10, cy - 8),
        (cx + 3, cy + 9),
        (cx - 1, cy + 3),
        (cx - 4, cy + 5),
    ]
    draw.polygon(points, fill=(255, 255, 255, 255))

    text_x = icon_x + icon_size + spacing
    text_y = y + (pill_h - th) // 2 - bbox[1] - 2
    draw.text((text_x + 1, text_y + 1), text, font=font, fill=(0, 0, 0, 180))
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))


# ============================================================
# TMDB lookup (Original Ultra-HD URLs with safe fallback)
# ============================================================

async def fetch_tmdb_backdrop_and_poster(imdb_id, title=None, year=None):
    if not imdb_id:
        return None, None

    headers = {
        "User-Agent": IMDB_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=headers) as session:
            find_url = f"{TMDB_API_URL}/find/{imdb_id}"
            async with session.get(
                find_url,
                params={"api_key": TMDB_KEY, "external_source": "imdb_id"},
            ) as response:
                if response.status != 200:
                    return None, None
                found = await response.json(content_type=None)

            results = (found.get("movie_results") or []) + (found.get("tv_results") or [])
            if not results:
                return None, None

            target_title = str(title or "").strip().casefold()
            target_year = str(year or "").strip()
            selected = None

            for item in results:
                item_title = str(item.get("title") or item.get("name") or item.get("original_title") or item.get("original_name") or "").strip()
                release = str(item.get("release_date") or item.get("first_air_date") or "")
                item_year = release[:4]

                if target_title and item_title.casefold() == target_title and (not target_year or item_year == target_year):
                    selected = item
                    break

            if selected is None and target_title:
                for item in results:
                    item_title = str(item.get("title") or item.get("name") or item.get("original_title") or item.get("original_name") or "").strip()
                    if item_title.casefold() == target_title:
                        selected = item
                        break

            selected = selected or results[0]
            backdrop_path = selected.get("backdrop_path")
            poster_path = selected.get("poster_path")

            backdrop_url = f"{TMDB_IMAGE_BASE}original{backdrop_path}" if backdrop_path else None
            poster_url = f"{TMDB_IMAGE_BASE}original{poster_path}" if poster_path else None

            return backdrop_url, poster_url

    except Exception as exc:
        print(f"TMDB Lookup Error [{imdb_id}]: {exc}", flush=True)
        return None, None


# ============================================================
# Download remote image
# ============================================================

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
    except Exception as exc:
        print(f"IMDb Image Download Error: {exc}", flush=True)
        return None


# ============================================================
# Main banner generator
# ============================================================

async def create_imdb_banner(info, bot_username=None):
    info = info or {}

    imdb_id = info.get("id")
    title = clean_text(info.get("title"), "Unknown Title")
    year = clean_text(info.get("year"), "N/A")
    rating = clean_text(info.get("rating"), "N/A")
    raw_runtime = clean_text(info.get("runtime"), "N/A")
    runtime = format_runtime_short(raw_runtime)
    storyline = clean_text(info.get("storyline"), "No storyline available.")
    genres = unique_strings(info.get("genres") or [])

    username = info.get("username") or info.get("bot_username") or bot_username or "@CinemaVeta"

    # --------------------------------------------------------
    # Fetch Original Ultra-HD Images
    # --------------------------------------------------------
    backdrop_url, tmdb_poster_url = await fetch_tmdb_backdrop_and_poster(imdb_id, title, year)

    poster = None
    if tmdb_poster_url:
        poster = await _download_image(tmdb_poster_url)
    if poster is None:
        poster = await _download_image(info.get("poster"))

    colors = _get_poster_color_palette(poster, count=4)
    dynamic_highlight = colors[1] if len(colors) > 1 else colors[0]

    background = await _download_image(backdrop_url)
    if background is None:
        background = poster
    if background is None:
        background = Image.new("RGB", (BANNER_WIDTH, BANNER_HEIGHT), (25, 25, 25))

    background = _cover_image(background, (BANNER_WIDTH, BANNER_HEIGHT))
    background = ImageEnhance.Brightness(background).enhance(0.72)
    background = background.filter(ImageFilter.BoxBlur(1))

    canvas = background.convert("RGBA")

    # --------------------------------------------------------
    # Fast Balanced Dark overlay
    # --------------------------------------------------------
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")

    left_x = 68
    text_right = 1060
    fade_end = text_right + 80

    for x in range(0, fade_end, 2):
        ratio = x / fade_end
        alpha = int(210 * ((1 - ratio) ** 1.15))
        od.line((x, 0, x, BANNER_HEIGHT), fill=(0, 0, 0, alpha), width=2)

    od.rectangle((0, 0, BANNER_WIDTH, BANNER_HEIGHT), fill=(0, 0, 0, 45))

    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------
    title_font = _font(62, True)
    rating_font = _font(30, True)
    body_bold = _font(24, True)
    pill_font = _font(22, True)
    small_font = _font(19, True)
    handle_font = _font(23, True)
    
    max_text_width = text_right - left_x

    # --------------------------------------------------------
    # Title & Rating Placement
    # --------------------------------------------------------
    title_lines = _wrap_text(draw, title.upper(), title_font, max_text_width - 230, max_lines=2)
    
    current_y = 175
    line_height = 74
    
    for idx, line in enumerate(title_lines):
        draw.text((left_x + 3, current_y + 3), line, font=title_font, fill=(0, 0, 0, 230))
        draw.text((left_x, current_y), line, font=title_font, fill=(255, 255, 255, 255))
        
        if idx == len(title_lines) - 1:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            last_line_width = bbox[2] - bbox[0]
            
            rating_x = left_x + min(last_line_width + 24, max_text_width - 190)
            
            draw.text((rating_x, current_y + 15), "★", font=_font(30, True), fill=(255, 193, 61, 255))
            draw.text((rating_x + 33, current_y + 16), rating, font=rating_font, fill=(255, 255, 255, 255))

            imdb_box_x = rating_x + 98
            draw.rounded_rectangle(
                (imdb_box_x, current_y + 16, imdb_box_x + 68, current_y + 48),
                radius=6, fill=(245, 197, 24, 255)
            )
            draw.text((imdb_box_x + 10, current_y + 20), "IMDb", font=small_font, fill=(0, 0, 0, 255))

            underline_w = min(150, max(110, last_line_width))
            draw.rounded_rectangle(
                (left_x, current_y + 76, left_x + underline_w, current_y + 81),
                radius=3, fill=dynamic_highlight
            )
            
        current_y += line_height

    # --------------------------------------------------------
    # Storyline (Overview)
    # --------------------------------------------------------
    story_y = current_y + 22
    story_lines_wrapped = _wrap_text(draw, storyline, body_bold, max_text_width, max_lines=4)

    for index, line in enumerate(story_lines_wrapped):
        draw.text(
            (left_x + 1, story_y + index * 41),
            line, font=body_bold, fill=(240, 240, 240, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 160)
        )

    # --------------------------------------------------------
    # Metadata Badges (Multi-Color Dynamic Contrast Pills)
    # --------------------------------------------------------
    pill_y = story_y + (len(story_lines_wrapped) * 41) + 26
    pill_x = left_x
    
    pill_items = []
    if runtime and runtime != "N/A":
        pill_items.append(runtime.upper())
    for genre in genres[:2]:
        pill_items.append(genre.upper())
    if year and year != "N/A":
        pill_items.append(str(year))

    for idx, item in enumerate(pill_items):
        cur_color = colors[idx % len(colors)]
        pill_fill = (cur_color[0], cur_color[1], cur_color[2], 245)

        rect = _draw_pill(
            canvas,
            (pill_x, pill_y),
            item,
            pill_font,
            fill=pill_fill,
            padding_x=20,
            padding_y=8,
            radius=18,
        )
        pill_x = rect[2] + 14

    # --------------------------------------------------------
    # Bottom Telegram Username Badge (Frosted Glass Blur)
    # --------------------------------------------------------
    tg_y = pill_y + 54
    _draw_telegram_badge(canvas, (left_x, tg_y), username, handle_font)

    # --------------------------------------------------------
    # Poster Card (Right side)
    # --------------------------------------------------------
    poster_box = (1125, 160, 1482, 704)
    px1, py1, px2, py2 = poster_box
    card_w = px2 - px1
    card_h = py2 - py1

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")
    sd.rounded_rectangle(
        (px1 + 10, py1 + 14, px2 + 10, py2 + 14),
        radius=22,
        fill=(0, 0, 0, 160),
    )
    shadow = shadow.filter(ImageFilter.BoxBlur(8))
    canvas = Image.alpha_composite(canvas, shadow)

    if poster is not None:
        inner_w = card_w - 14
        inner_h = card_h - 14

        poster_resized = _cover_image(poster, (inner_w, inner_h))
        mask = _rounded_mask((inner_w, inner_h), 18)

        poster_rgba = poster_resized.convert("RGBA")
        poster_rgba.putalpha(mask)

        canvas.alpha_composite(poster_rgba, (px1 + 7, py1 + 7))

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        poster_box,
        radius=23,
        outline=(255, 255, 255, 255),
        width=7,
    )

    # --------------------------------------------------------
    # Export Lossless Master Quality
    # --------------------------------------------------------
    output = io.BytesIO()
    final_render = canvas.convert("RGB")
    final_render.save(
        output,
        format="JPEG",
        quality=98,
        subsampling=0,
        optimize=True,
    )
    output.seek(0)
    output.name = "imdb_banner.jpg"

    return output
