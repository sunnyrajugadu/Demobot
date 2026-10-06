import io
import re

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ============================================================
# IMDb Custom Banner Generator
# File: utils/imdb_banner.py
# ============================================================

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"

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

def _get_dominant_color(image):
    """Gets the average color of the image to tint pills perfectly."""
    if not image:
        return (205, 147, 82)
    try:
        avg = image.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))
        if isinstance(avg, int):
            return (avg, avg, avg)
        if len(avg) >= 3:
            r, g, b = avg[:3]
            
            # Boost brightness for readability & aesthetics
            r = min(255, int(r * 1.5))
            g = min(255, int(g * 1.5))
            b = min(255, int(b * 1.5))
            
            # Prevent pure black/too dark
            if max(r, g, b) < 90:
                r, g, b = 100, 100, 100
                
            return (r, g, b)
    except:
        pass
    return (205, 147, 82)


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
    fill=(35, 35, 35, 180),
    outline=(255, 255, 255, 90),
    text_fill=(255, 255, 255, 255),
    padding_x=18,
    padding_y=9,
    radius=22,
):
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

    draw.rounded_rectangle(
        rect,
        radius=radius,
        fill=fill,
        outline=outline,
        width=1,
    )

    draw.text(
        (x + padding_x, y + padding_y - bbox[1]),
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

                found = await response.json(content_type=None)

            results = (
                found.get("movie_results")
                or found.get("tv_results")
                or []
            )

            if not results:
                return None, None

            target_title = str(title or "").strip().casefold()
            target_year = str(year or "").strip()
            selected = None

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
            backdrop_path = selected.get("backdrop_path")
            poster_path = selected.get("poster_path")

            # Fetch 'original' high quality images
            backdrop_url = (
                f"{TMDB_IMAGE_BASE}original{backdrop_path}"
                if backdrop_path
                else None
            )

            poster_url = (
                f"{TMDB_IMAGE_BASE}original{poster_path}"
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

async def _download_image(url, keep_alpha=False):
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

        img = Image.open(io.BytesIO(raw))
        
        if keep_alpha and img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            return img.convert("RGBA")
            
        return img.convert("RGB")

    except Exception as exc:
        print(
            f"IMDb Image Download Error: {exc}",
            flush=True,
        )
        return None


# ============================================================
# Main banner generator
# ============================================================

async def create_imdb_banner(info):
    info = info or {}

    imdb_id = info.get("id")
    title = clean_text(info.get("title"), "Unknown Title")
    year = clean_text(info.get("year"), "N/A")
    rating = clean_text(info.get("rating"), "N/A")
    runtime = clean_text(info.get("runtime"), "N/A")
    storyline = clean_text(info.get("storyline"), "No storyline available.")
    genres = unique_strings(info.get("genres") or [])

    # --------------------------------------------------------
    # Fetch TMDB backdrop + poster (Fallback to IMDb)
    # --------------------------------------------------------
    backdrop_url, tmdb_poster_url = await fetch_tmdb_backdrop_and_poster(imdb_id, title, year)

    background = await _download_image(backdrop_url)
    if background is None:
        background = await _download_image(info.get("poster"))

    if background is None:
        background = Image.new("RGB", (BANNER_WIDTH, BANNER_HEIGHT), (25, 25, 25))

    background = _cover_image(background, (BANNER_WIDTH, BANNER_HEIGHT))
    background = background.filter(ImageFilter.GaussianBlur(radius=1.2))
    
    # Extract Dominant Color for dynamic elements
    dom_r, dom_g, dom_b = _get_dominant_color(background)
    
    # Setup dynamic colors
    pill_fill = (dom_r, dom_g, dom_b, 195)
    pill_outline = (dom_r, dom_g, dom_b, 255)
    dynamic_highlight = (dom_r, dom_g, dom_b, 255)
    
    canvas = background.convert("RGBA")

    # --------------------------------------------------------
    # Cinematic dark overlay (Gradient fade style)
    # --------------------------------------------------------
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")

    left_x = 68
    text_right = 1040
    fade_end = text_right + 50

    # Gradient overlay ONLY where text sits, fading out towards the poster
    for x in range(BANNER_WIDTH):
        if x < fade_end:
            ratio = x / fade_end
            alpha = int(160 * ((1 - ratio) ** 1.3))
        else:
            alpha = 0
        od.line((x, 0, x, BANNER_HEIGHT), fill=(0, 0, 0, alpha))

    # Extremely light global dark tint just to bind it together
    od.rectangle((0, 0, BANNER_WIDTH, BANNER_HEIGHT), fill=(0, 0, 0, 5))

    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------
    title_font = _font(64, True)
    rating_font = _font(30, True)
    body_bold = _font(25, True)
    pill_font = _font(22, True)
    small_font = _font(19, True)
    
    max_text_width = text_right - left_x

    # --------------------------------------------------------
    # Title (Wrapped to multiple lines if long)
    # --------------------------------------------------------
    # max_lines = 3 allows very long titles to wrap perfectly
    title_lines = _wrap_text(draw, title.upper(), title_font, max_text_width - 220, max_lines=3)
    
    current_y = 160 
    line_height = 75
    
    for idx, line in enumerate(title_lines):
        # Drop shadow
        draw.text((left_x + 4, current_y + 5), line, font=title_font, fill=(0, 0, 0, 180))
        # Main text
        draw.text((left_x, current_y), line, font=title_font, fill=(255, 255, 255, 255))
        
        # Add rating & underline next to the LAST line of the title
        if idx == len(title_lines) - 1:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            last_line_width = bbox[2] - bbox[0]
            
            rating_x = left_x + min(last_line_width + 24, max_text_width - 190)
            
            # IMDb Rating (★ + Score)
            draw.text((rating_x, current_y + 15), "★", font=_font(30, True), fill=(255, 193, 61, 255))
            draw.text((rating_x + 33, current_y + 16), rating, font=rating_font, fill=(255, 255, 255, 255))

            # IMDb Badge (Black bg, Yellow text)
            imdb_box_x = rating_x + 105
            draw.rounded_rectangle(
                (imdb_box_x, current_y + 12, imdb_box_x + 78, current_y + 52),
                radius=10, fill=(0, 0, 0, 255), outline=(245, 190, 35, 255), width=1
            )
            draw.text((imdb_box_x + 13, current_y + 18), "IMDb", font=small_font, fill=(245, 190, 35, 255))

            # Dynamic Line under title
            underline_w = min(165, max(95, last_line_width))
            draw.rounded_rectangle(
                (left_x, current_y + 78, left_x + underline_w, current_y + 83),
                radius=3, fill=dynamic_highlight
            )
            
        current_y += line_height


    # --------------------------------------------------------
    # Storyline (Dynamic Y positioning)
    # --------------------------------------------------------
    story_y = current_y + 20
    
    # Adjust max story lines so they don't overflow the bottom if title is very long
    max_story_lines = max(1, 5 - len(title_lines))
    story_lines_wrapped = _wrap_text(draw, storyline, body_bold, max_text_width, max_lines=max_story_lines)

    for index, line in enumerate(story_lines_wrapped):
        draw.text(
            (left_x + 2, story_y + index * 43),
            line, font=body_bold, fill=(255, 255, 255, 245),
            stroke_width=1, stroke_fill=(0, 0, 0, 125)
        )

    # --------------------------------------------------------
    # Information pills (Dynamic Colors & Filtered Content)
    # --------------------------------------------------------
    pill_y = story_y + (len(story_lines_wrapped) * 43) + 30
    pill_x = left_x
    
    # Only keep Runtime, Genres(2 max), Year
    pill_items = []
    if runtime and runtime != "N/A":
        pill_items.append(runtime)
    
    for genre in genres[:2]:
        pill_items.append(genre.upper())
        
    if year and year != "N/A":
        pill_items.append(year)

    pills_right = 1035

    for item in pill_items:
        item_text = str(item).strip()
        if not item_text or pill_x >= pills_right:
            break

        bbox = draw.textbbox((0, 0), item_text, font=pill_font)
        text_width = bbox[2] - bbox[0]
        padding_x = 18
        pill_width = text_width + (padding_x * 2)

        if pill_x + pill_width > pills_right:
            break

        # Apply the dominant color dynamic background!
        rect = _draw_pill(
            canvas,
            (pill_x, pill_y),
            item_text,
            pill_font,
            fill=pill_fill,
            outline=pill_outline,
            text_fill=(255, 255, 255, 255),
            padding_x=padding_x,
            padding_y=8,
            radius=20,
        )
        pill_x = rect[2] + 12

    # --------------------------------------------------------
    # Poster card
    # --------------------------------------------------------
    poster = None
    if tmdb_poster_url:
        poster = await _download_image(tmdb_poster_url)
    if poster is None:
        poster = await _download_image(info.get("poster"))

    poster_box = (1125, 160, 1482, 704)
    px1, py1, px2, py2 = poster_box
    card_w = px2 - px1
    card_h = py2 - py1

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")

    sd.rounded_rectangle(
        (px1 + 10, py1 + 14, px2 + 10, py2 + 14),
        radius=22,
        fill=(0, 0, 0, 145),
    )

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
    draw.rounded_rectangle(
        poster_box,
        radius=23,
        outline=(255, 255, 255, 245),
        width=7,
    )

    # --------------------------------------------------------
    # Export 100% Quality JPEG
    # --------------------------------------------------------
    output = io.BytesIO()
    canvas.convert("RGB").save(
        output,
        format="JPEG",
        quality=100,          # 95 nundi 100 ki pencham
        subsampling=0,        # Color blur avvakunda aputhundi
        optimize=True,
    )
    output.seek(0)
    output.name = "imdb_banner.jpg"

    return output
