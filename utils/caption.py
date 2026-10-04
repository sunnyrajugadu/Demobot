import html

from utils.rename import clean_file_name


# ============================================================
# SIZE FORMAT
# ============================================================

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


# ============================================================
# FILE CAPTION
# ============================================================

def make_file_caption(file):
    """
    Final sent-file caption.

    Format:

    @CinemaVetaBot -
    @mrDuDeHoLic - Movie Filename.mkv
    Size :- 2.80 GB

    IMPORTANT:
    - @CinemaVetaBot is bold + clickable
    - @mrDuDeHoLic is bold + clickable
    - Filename is cleaned using clean_file_name()
    - Only unwanted leading prefixes are removed
    - Remaining filename is preserved
    - File size comes from database
    - No metadata is rebuilt into filename
    - No extra source/channel information is added
    """


    # ========================================================
    # GET INDEXED FILE NAME
    # ========================================================

    raw_name = (
        file.get("file_name")
        or file.get("original_file_name")
        or file.get("movie_name")
        or ""
    )


    # ========================================================
    # CLEAN FILE NAME
    # ========================================================

    file_name = clean_file_name(
        raw_name
    )


    if not file_name:
        file_name = "Movie"


    # ========================================================
    # FILE SIZE
    # ========================================================

    size = format_size(
        file.get(
            "file_size_bytes",
            0
        )
    )


    # ========================================================
    # HTML ESCAPE
    # ========================================================

    safe_file_name = html.escape(
        str(file_name)
    )

    safe_size = html.escape(
        str(size)
    )


    # ========================================================
    # FINAL CAPTION
    # ========================================================

    return (
        '<a href="https://t.me/CinemaVetaBot">'
        '<b>@CinemaVetaBot -</b>'
        '</a>\n'

        '<a href="https://t.me/mrDuDeHoLic">'
        '<b>@mrDuDeHoLic -</b>'
        '</a> '

        f'<b>{safe_file_name}\n'
        f'Size :- {safe_size}</b>'
    )
