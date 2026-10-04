# ============================================================
# METADATA EXTRACTOR (PRE-COMPILED ULTRA-FAST ENGINE)
# ============================================================

import re
from functools import lru_cache

# ============================================================
# DETECTORS
# ============================================================

from utils.detectors import (
    detect_year,
    detect_quality,
    detect_languages,
    detect_language,
    detect_audio,
    detect_audio_type,
    detect_channels,
    detect_source,
    detect_release_type,
    detect_video_codec,
    detect_hdr,
    detect_bit_depth,
    detect_scan_type,
    detect_fps,
    detect_resolution,
    detect_aspect_ratio,
    detect_edition,
    detect_subtitles,
    detect_container,
    detect_file_size,
    detect_release_flags,
)


# ============================================================
# PRE-COMPILED REGEX CONSTANTS
# ============================================================

_RE_URL = re.compile(
    r"https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|telegram\.dog/\S+",
    re.IGNORECASE,
)
_RE_LEADING_AT = re.compile(r"^\s*@+")
_RE_TG_USERNAME = re.compile(r"(?<!\w)@[\w]{3,}")
_RE_FILE_SIZE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:TB|GB|MB|KB)\b", re.IGNORECASE)
_RE_PROTECTED_ERA = re.compile(r"\b\d{3,4}\s+(?:AD|BC|BCE|CE)\b", re.IGNORECASE)
_RE_PAREN_YEAR = re.compile(r"[\(\[\{]\s*(?:19\d{2}|20\d{2})\s*[\)\]\}]")
_RE_SEP_YEAR = re.compile(r"(?<!\d)(?:19\d{2}|20\d{2})(?=\s*(?:[-_.|]|$))")
_RE_KEYWORD_YEAR = re.compile(
    r"(?<!\d)(?:19\d{2}|20\d{2})(?=\s+(?:Telugu|Hindi|Tamil|Malayalam|Kannada|English|WEB|WEB-DL|WEBRip|HDRip|BluRay|720p|1080p|2160p|x264|x265|HEVC)\b)",
    re.IGNORECASE,
)
_RE_EXT = re.compile(r"\.[a-zA-Z0-9]{2,8}$")
_RE_DIMENSIONS = re.compile(r"(?<!\d)\d{3,5}\s*x\s*\d{3,5}(?!\d)", re.IGNORECASE)
_RE_FPS = re.compile(
    r"\b(?:23[\s._]?976|24|25|29[\s._]?97|30|50|59[\s._]?94|60)\s*fps\b",
    re.IGNORECASE,
)
_RE_CODEC_LEFTOVER = re.compile(
    r"(?<!\w)(?:x264|x265|h264|h265|h266|hevc|av1|avc|vvc)(?!\w)",
    re.IGNORECASE,
)
_RE_EMPTY_PARENS = re.compile(r"\(\s*\)")
_RE_EMPTY_BRACKETS = re.compile(r"\[\s*\]")
_RE_EMPTY_BRACES = re.compile(r"\{\s*\}")
_RE_DOT_UNDERSCORE = re.compile(r"[._]+")
_RE_MULTI_HYPHEN = re.compile(r"[-]{2,}")
_RE_PIPE = re.compile(r"[|]+")
_RE_ALLOWED_CHARS = re.compile(r"[^\w\s\-\(\)\[\]&,:!'’]")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_SPLIT_SEPS = re.compile(r"[_\-.]+")

_RE_METADATA_COMBINED = re.compile(
    r"(?:"
    # RESOLUTION
    r"\b4320p\b|\b2160p\b|\b1440p\b|\b1080p\b|\b1080i\b|\b720p\b|\b576p\b|\b480p\b|\b360p\b|\b240p\b|"
    r"\b8k\b|\b4k\b|\b2k\b|\buhd\b|\bfhd\b|\bfull[-_. ]?hd\b|\bhd\b|"
    # SOURCES
    r"\bWEB[-_. ]?DL\b|\bWEB[-_. ]?Rip\b|\bWEBHD\b|\bWEB\b|\bBlu[-_. ]?Ray\b|\bBluRay\b|\bUHD[-_. ]?BluRay\b|"
    r"\bBRRip\b|\bBDRip\b|\bBDRemux\b|\bRemux\b|\bHDRip\b|\bHDTVRip\b|\bHDTV\b|\bDVDRip\b|\bDVD\b|\bTVRip\b|"
    r"\bHDCAM\b|\bCAM\b|\bTelesync\b|\bTelecine\b|\bScreener\b|\bWorkprint\b|"
    # STREAMING
    r"\bAMZN\b|\bAmazon\b|\bNetflix\b|\bNF\b|\bDisney\+?\b|\bDSNP\b|\bHMAX\b|\bHBO[-_. ]?Max\b|\bATVP\b|\bApple[-_. ]?TV\b|"
    r"\bPCOK\b|\bPeacock\b|\bHulu\b|\bZEE5\b|\bJioCinema\b|\bHotstar\b|\bSonyLIV\b|"
    # HDR
    r"\bHDR10\+?\b|\bHDR10Plus\b|\bHDR\b|\bDolby[-_. ]?Vision\b|\bDolbyVision\b|\bDV\b|\bHLG\b|"
    # VIDEO CODECS
    r"\bHEVC\b|\bx265\b|\bx264\b|\bH[-_. ]?264\b|\bH[-_. ]?265\b|\bH[-_. ]?266\b|\bAVC\b|\bVVC\b|\bAV1\b|\bVP9\b|"
    r"\bMPEG[-_. ]?4\b|\bMPEG[-_. ]?2\b|\bMP4V\b|\bXviD\b|\bDivX\b|"
    # BIT DEPTH
    r"\b12[-_. ]?bit\b|\b10[-_. ]?bit\b|\b8[-_. ]?bit\b|\b12bit\b|\b10bit\b|\b8bit\b|"
    # AUDIO TYPE
    r"\bDual[-_. ]?Audio\b|\bMulti[-_. ]?Audio\b|\bMulti[-_. ]?Language\b|"
    # AUDIO FORMATS
    r"\bTrueHD\b|\bAtmos\b|\bDTS[-_. ]?HD\b|\bDTS[-_. ]?X\b|\bDTSX\b|\bDTS\b|\bDolby[-_. ]?Digital[-_. ]?Plus\b|"
    r"\bDolby[-_. ]?Digital\b|\bE[-_. ]?AC3\b|\bEAC3\b|\bDDP\b|\bDD\+\b|\bAC3\b|\bAAC\b|\bFLAC\b|\bOPUS\b|\bMP3\b|\bPCM\b|"
    # CHANNELS
    r"\b7[\s._-]?1\b|\b6[\s._-]?1\b|\b5[\s._-]?1\b|\b2[\s._-]?1\b|\b2[\s._-]?0\b|"
    # LANGUAGES
    r"\bTelugu\b|\bTelu\b|\bTelegu\b|\bTel\b|\bHindi\b|\bHin\b|\bTamil\b|\bTam\b|\bMalayalam\b|\bMal\b|\bKannada\b|\bKan\b|\bEnglish\b|\bEng\b|"
    # SUBTITLES
    r"\bESub\b|\bESubs\b|\bSub\b|\bSubs\b|\bSubtitle\b|\bSubtitles\b|"
    # EDITIONS
    r"\bDirector['’]?s[-_. ]?Cut\b|\bDirectors[-_. ]?Cut\b|\bExtended[-_. ]?Cut\b|\bExtended[-_. ]?Edition\b|\bUnrated\b|\bUncut\b|"
    r"\bRemastered\b|\bRestored\b|\bAnniversary[-_. ]?Edition\b|\bCollector['’]?s[-_. ]?Edition\b|\bSpecial[-_. ]?Edition\b|\bUltimate[-_. ]?Edition\b|\bIMAX\b|"
    # RELEASE FLAGS
    r"\bHYBRID\b|\bREMASTERED\b|\bREMASTER\b|\bREPACK\b|\bPROPER\b|\bREMSTERED\b|\bUNCUT\b|\bEXTENDED\b|\bORG\b|\bORIGINAL\b|\bNEW\b|\bFINAL\b|\bCOMPLETE\b|\bTRUE\b|\bTHEATRICAL\b|\bRELEASE\b|"
    # CONTAINERS
    r"\bMatroska\b|\bMKV\b|\bMP4\b|\bAVI\b|\bMOV\b|\bMPEG\b|\bWEBM\b|\bM2TS\b"
    r")",
    re.IGNORECASE,
)

_FRAG_RES = re.compile(
    r"^(?:240p|360p|480p|576p|720p|1080i|1080p|1440p|2160p|4320p|2k|4k|8k|hd|fhd|uhd)$",
    re.IGNORECASE,
)
_FRAG_FPS = re.compile(
    r"^(?:23[._ ]?976|24|25|29[._ ]?97|30|50|59[._ ]?94|60)[ _.-]?fps$",
    re.IGNORECASE,
)
_FRAG_SIZE = re.compile(r"^\d+(?:\.\d+)?\s*(?:tb|gb|mb|kb)$", re.IGNORECASE)
_FRAG_CHANNELS = re.compile(r"^\d[\s._-]?[01]$")
_FRAG_COMBINED = re.compile(
    r"^(?:1080p|720p|2160p|4320p|x264|x265|h264|h265|hevc|av1|10bit|12bit|8bit|5[._-]?1|7[._-]?1|2[._-]?0|ddp[._-]?\d*|dts[._-]?\w*)$",
    re.IGNORECASE,
)

METADATA_WORDS_SET = {
    "web", "webdl", "web-dl", "webrip", "web-rip", "webhd", "bluray", "blu-ray", "brrip", "bdrip",
    "bdremux", "remux", "hdrip", "hdtv", "hdtvrip", "tvrip", "dvdrip", "dvd", "hdcam", "cam",
    "telesync", "telecine", "screener", "workprint", "amzn", "amazon", "netflix", "nf", "dsnp",
    "disney", "disney+", "hmax", "hbo", "atvp", "apple", "pcok", "peacock", "hulu", "zee5",
    "jiocinema", "hotstar", "sonyliv", "hdr", "hdr10", "hdr10+", "hdr10plus", "dolbyvision",
    "dolby-vision", "dv", "hlg", "hevc", "x264", "x265", "h264", "h265", "h266", "avc", "vvc",
    "av1", "vp9", "mpeg4", "mpeg-4", "mpeg2", "mpeg-2", "mp4v", "xvid", "divx", "12bit", "10bit",
    "8bit", "truehd", "atmos", "dts", "dts-hd", "dtsx", "dts-x", "dolby", "dolbydigital",
    "dolby-digital", "dolbydigitalplus", "dolby-digital-plus", "eac3", "e-ac3", "ddp", "dd+",
    "ac3", "aac", "flac", "opus", "mp3", "pcm", "dual", "dualaudio", "dual-audio", "multiaudio",
    "multi-audio", "multilanguage", "multi-language", "telugu", "telu", "telegu", "tel", "hindi",
    "hin", "tamil", "tam", "malayalam", "mal", "kannada", "kan", "english", "eng", "esub", "esubs",
    "sub", "subs", "subtitle", "subtitles", "directorscut", "director'scut", "director’scut",
    "extendedcut", "extendededition", "unrated", "uncut", "remastered", "restored",
    "anniversaryedition", "collectorsedition", "collector'sedition", "collector’sedition",
    "specialedition", "ultimateedition", "imax", "hybrid", "remaster", "repack", "proper",
    "org", "original", "new", "final", "complete", "true", "theatrical", "release",
    "matroska", "mkv", "mp4", "avi", "mov", "mpeg", "webm", "m2ts",
}

UPLOADER_INDICATORS = (
    "movie", "movies", "movie4u", "movies4u", "cinema", "cinemas", "cine", "film", "films",
    "flix", "bot", "official", "channel", "telegram", "tg", "telugumovies", "tamilmovies",
    "hindimovies", "malayalammovies", "kannadamovies", "4u", "hub", "media", "world",
    "zone", "club", "group", "team", "network",
)


# ============================================================
# TEXT HELPERS
# ============================================================

def _text(value):
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def _list(value):
    if value is None:
        return ["Unknown"]
    if isinstance(value, str):
        val = value.strip()
        return [val] if val else ["Unknown"]
    try:
        result = [_text(item) for item in value if _text(item)]
        if result:
            return result
    except (TypeError, ValueError):
        pass
    return ["Unknown"]


def _value(value):
    v = _text(value)
    return v if v else "Unknown"


# ============================================================
# METADATA FRAGMENT CHECK
# ============================================================

def _looks_like_metadata_fragment(value):
    token = _text(value)
    if not token:
        return True

    clean = token.strip("[](){}.,-_ ")
    if not clean:
        return True

    low = clean.lower()

    if _FRAG_RES.match(low):
        return True
    if _FRAG_FPS.match(low):
        return True
    if _FRAG_SIZE.match(low):
        return True
    if _FRAG_CHANNELS.match(clean):
        return True
    if low in METADATA_WORDS_SET:
        return True
    if _FRAG_COMBINED.match(low):
        return True

    return False


# ============================================================
# SMART YEAR REMOVAL
# ============================================================

def _remove_release_years(name):
    name = _text(name)
    if not name:
        return ""

    protected = []

    def _protect(match):
        value = match.group(0)
        marker = f"__PROTECTED_TITLE_{len(protected)}__"
        protected.append(value)
        return marker

    name = _RE_PROTECTED_ERA.sub(_protect, name)
    name = _RE_PAREN_YEAR.sub(" ", name)
    name = _RE_SEP_YEAR.sub(" ", name)
    name = _RE_KEYWORD_YEAR.sub(" ", name)

    for index, value in enumerate(protected):
        name = name.replace(f"__PROTECTED_TITLE_{index}__", value)

    return name


# ============================================================
# LEADING UPLOADER / CHANNEL PREFIX CLEANER
# ============================================================

def _remove_leading_uploader_prefix(name):
    name = _text(name)
    if not name or not name.startswith("@"):
        return name

    name = _RE_LEADING_AT.sub("", name).strip()
    if not name:
        return ""

    temp = _RE_SPLIT_SEPS.sub(" ", name)
    temp = _RE_WHITESPACE.sub(" ", temp).strip()
    if not temp:
        return ""

    words = temp.split()
    if len(words) <= 1:
        return ""

    indicator_index = -1
    for index, word in enumerate(words):
        low = word.lower()
        if any(marker in low for marker in UPLOADER_INDICATORS):
            indicator_index = index

    if indicator_index >= 0:
        title_words = words[indicator_index + 1 :]
        if title_words:
            return " ".join(title_words)

    raw_parts = [part.strip() for part in _RE_SPLIT_SEPS.split(name) if part.strip()]
    if len(raw_parts) >= 2:
        first = raw_parts[0]
        first_low = first.lower()
        strong_channel = (
            first_low.endswith(
                ("bot", "cinema", "cinemas", "movies", "movie", "flix", "channel", "official", "media", "hub", "4u")
            )
            or any(char.isdigit() for char in first)
        )
        if strong_channel:
            return " ".join(raw_parts[1:])

    return " ".join(words)


# ============================================================
# MOVIE NAME EXTRACTOR
# ============================================================

def _clean_bracket(match):
    content = _text(match.group(2))
    if not content:
        return " "

    tokens = [t for t in re.split(r"[\s._,\-+/|]+", content) if t]
    if tokens and all(_looks_like_metadata_fragment(t) for t in tokens):
        return " "

    return match.group(0)


_RE_PARENS_CONTENT = re.compile(r"(\()([^)]+)(\))")
_RE_BRACKETS_CONTENT = re.compile(r"(\[)([^]]+)(\])")
_RE_BRACES_CONTENT = re.compile(r"(\{)([^}]+)(\})")


@lru_cache(maxsize=16384)
def extract_movie_name(filename: str):
    if not filename:
        return "Unknown"

    name = _text(filename)
    if not name:
        return "Unknown"

    for _ in range(3):
        new_name = _RE_EXT.sub("", name)
        if new_name == name:
            break
        name = new_name

    name = _RE_URL.sub(" ", name)
    name = _remove_leading_uploader_prefix(name)
    name = _RE_TG_USERNAME.sub(" ", name)
    name = _RE_FILE_SIZE.sub(" ", name)
    name = _remove_release_years(name)

    name = _RE_METADATA_COMBINED.sub(" ", name)
    name = _RE_DIMENSIONS.sub(" ", name)
    name = _RE_FPS.sub(" ", name)
    name = _RE_FILE_SIZE.sub(" ", name)
    name = _RE_CODEC_LEFTOVER.sub(" ", name)

    name = _RE_PARENS_CONTENT.sub(_clean_bracket, name)
    name = _RE_BRACKETS_CONTENT.sub(_clean_bracket, name)
    name = _RE_BRACES_CONTENT.sub(_clean_bracket, name)

    name = _RE_EMPTY_PARENS.sub(" ", name)
    name = _RE_EMPTY_BRACKETS.sub(" ", name)
    name = _RE_EMPTY_BRACES.sub(" ", name)

    name = _RE_DOT_UNDERSCORE.sub(" ", name)
    name = _RE_MULTI_HYPHEN.sub(" ", name)
    name = _RE_PIPE.sub(" ", name)

    name = _RE_ALLOWED_CHARS.sub(" ", name)

    name = _RE_EMPTY_PARENS.sub(" ", name)
    name = _RE_EMPTY_BRACKETS.sub(" ", name)
    name = _RE_EMPTY_BRACES.sub(" ", name)

    name = _RE_WHITESPACE.sub(" ", name).strip()
    name = name.strip(" -_.")

    return name or "Unknown"


# ============================================================
# ALL METADATA AGGREGATOR
# ============================================================

def extract_metadata(filename: str, caption: str = ""):
    filename = _text(filename)
    caption = _text(caption)

    combined_text = f"{filename}\n{caption}" if caption else filename
    movie_name = extract_movie_name(filename)

    year = detect_year(combined_text)
    quality = detect_quality(combined_text)
    languages = detect_languages(combined_text)
    language = detect_language(combined_text)
    audio = detect_audio(combined_text)
    audio_type = detect_audio_type(combined_text)
    channels = detect_channels(combined_text)
    source = detect_source(combined_text)
    release_type = detect_release_type(combined_text)
    video_codec = detect_video_codec(combined_text)
    hdr = detect_hdr(combined_text)
    bit_depth = detect_bit_depth(combined_text)
    scan_type = detect_scan_type(combined_text)
    fps = detect_fps(combined_text)
    resolution = detect_resolution(combined_text)
    aspect_ratio = detect_aspect_ratio(combined_text)
    edition = detect_edition(combined_text)
    subtitles = detect_subtitles(combined_text)
    container = detect_container(combined_text)
    file_size = detect_file_size(combined_text)
    release_flags = detect_release_flags(combined_text)

    return {
        "movie_name": _value(movie_name),
        "year": _value(year),
        "languages": _list(languages),
        "language": _value(language),
        "quality": _value(quality),
        "resolution": _value(resolution),
        "video_codec": _value(video_codec),
        "hdr": _value(hdr),
        "bit_depth": _value(bit_depth),
        "scan_type": _value(scan_type),
        "fps": _value(fps),
        "aspect_ratio": _value(aspect_ratio),
        "audio": _value(audio),
        "audio_type": _value(audio_type),
        "channels": _value(channels),
        "source": _value(source),
        "release_type": _value(release_type),
        "edition": _value(edition),
        "release_flags": _list(release_flags),
        "subtitles": _value(subtitles),
        "container": _value(container),
        "file_size": _value(file_size),
    }

# ============================================================
# END OF METADATA.PY
# ============================================================
