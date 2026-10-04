# ============================================================
# DETECTORS.PY
# PRODUCTION-GRADE PRE-COMPILED ULTRA-FAST DETECTION ENGINE
# ============================================================

import re
from functools import lru_cache

# ============================================================
# PRE-COMPILED COMMON REGEX
# ============================================================

_RE_URL = re.compile(
    r"https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|telegram\.dog/\S+",
    re.IGNORECASE,
)
_RE_TG_USER = re.compile(r"(?<!\w)@[\w_]{3,}")
_RE_SEPARATORS_1 = re.compile(r"[_\-.]+")
_RE_SEPARATORS_2 = re.compile(r"[/\\|+]+")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_DIMENSIONS = re.compile(r"(?<!\d)(\d{3,5})\s*x\s*(\d{3,5})(?!\d)", re.IGNORECASE)
_RE_BRACKET_YEAR = re.compile(r"[\(\[\{]\s*((?:19|20)\d{2})\s*[\)\]\}]", re.IGNORECASE)
_RE_STANDALONE_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)", re.IGNORECASE)
_RE_DUAL_AUDIO = re.compile(r"\bdual\s*audio\b", re.IGNORECASE)
_RE_MULTI_AUDIO = re.compile(r"\bmulti\s*audio\b|\bmulti\s*language\b", re.IGNORECASE)
_RE_FILE_SIZE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(TB|GB|MB|KB)(?!\w)", re.IGNORECASE)

# ============================================================
# COMMON HELPERS
# ============================================================

def _text(value):
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""

@lru_cache(maxsize=16384)
def _normalize_for_detection(value):
    text = _text(value)
    if not text:
        return ""

    text = _RE_URL.sub(" ", text)
    text = _RE_TG_USER.sub(" ", text)
    text = _RE_SEPARATORS_1.sub(" ", text)
    text = _RE_SEPARATORS_2.sub(" ", text)

    text = (
        text.replace("’", "'")
        .replace("[", " ")
        .replace("]", " ")
        .replace("(", " ")
        .replace(")", " ")
    )

    return _RE_WHITESPACE.sub(" ", text).strip()

@lru_cache(maxsize=16384)
def _normalized_lower(value):
    return _normalize_for_detection(value).lower()

def _contains_token(text, token):
    text = _text(text)
    token = _text(token)
    if not text or not token:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text, flags=re.IGNORECASE))

def _first_match(text, patterns):
    if not text:
        return "Unknown"
    for label, pattern in patterns:
        if pattern.search(text):
            return label
    return "Unknown"

def _all_matches(text, patterns):
    found = []
    if not text:
        return found
    for label, pattern in patterns:
        if pattern.search(text):
            if label not in found:
                found.append(label)
    return found

def _dedupe(values):
    return list(dict.fromkeys(values))

# ============================================================
# YEAR DETECTOR
# ============================================================

@lru_cache(maxsize=8192)
def detect_year(name: str):
    text = _text(name)
    if not text:
        return "Unknown"

    bracket_matches = _RE_BRACKET_YEAR.findall(text)
    for value in reversed(bracket_matches):
        try:
            year = int(value)
            if 1900 <= year <= 2099:
                return str(year)
        except (TypeError, ValueError):
            continue

    matches = _RE_STANDALONE_YEAR.findall(text)
    valid = []
    for value in matches:
        try:
            year = int(value)
            if 1900 <= year <= 2099:
                valid.append(year)
        except (TypeError, ValueError):
            continue

    if not valid:
        return "Unknown"

    return str(valid[0])

# ============================================================
# QUALITY DETECTOR
# ============================================================

_QUALITY_PATTERNS = [
    ("8K", re.compile(r"\b8k\b|\b4320p\b", re.IGNORECASE)),
    ("4K", re.compile(r"\b4k\b|\b2160p\b|\buhd\b", re.IGNORECASE)),
    ("2K", re.compile(r"\b2k\b|\b1440p\b", re.IGNORECASE)),
    ("1080p", re.compile(r"\b1080p\b|\b1080i\b|\bfhd\b|\bfull\s+hd\b", re.IGNORECASE)),
    ("720p", re.compile(r"\b720p\b", re.IGNORECASE)),
    ("576p", re.compile(r"\b576p\b", re.IGNORECASE)),
    ("480p", re.compile(r"\b480p\b", re.IGNORECASE)),
    ("360p", re.compile(r"\b360p\b", re.IGNORECASE)),
    ("240p", re.compile(r"\b240p\b", re.IGNORECASE)),
    ("HD", re.compile(r"\bhd\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_quality(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    result = _first_match(text, _QUALITY_PATTERNS)
    if result != "Unknown":
        return result

    try:
        match = _RE_DIMENSIONS.search(text)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            if width >= 7000 and height >= 3500:
                return "8K"
            if width >= 3500 and height >= 1800:
                return "4K"
            if width >= 2400 and height >= 1200:
                return "2K"
            if width >= 1800 and height >= 950:
                return "1080p"
            if width >= 1100 and height >= 650:
                return "720p"
            if width >= 600 and height >= 350:
                return "SD"
    except (TypeError, ValueError):
        pass

    return "Unknown"

# ============================================================
# RESOLUTION DETECTOR
# ============================================================

_RESOLUTION_PATTERNS = [
    ("4320p", re.compile(r"\b4320p\b", re.IGNORECASE)),
    ("2160p", re.compile(r"\b2160p\b", re.IGNORECASE)),
    ("1440p", re.compile(r"\b1440p\b", re.IGNORECASE)),
    ("1080p", re.compile(r"\b1080p\b", re.IGNORECASE)),
    ("1080i", re.compile(r"\b1080i\b", re.IGNORECASE)),
    ("720p", re.compile(r"\b720p\b", re.IGNORECASE)),
    ("576p", re.compile(r"\b576p\b", re.IGNORECASE)),
    ("480p", re.compile(r"\b480p\b", re.IGNORECASE)),
    ("360p", re.compile(r"\b360p\b", re.IGNORECASE)),
    ("240p", re.compile(r"\b240p\b", re.IGNORECASE)),
    ("8K", re.compile(r"\b8k\b", re.IGNORECASE)),
    ("4K", re.compile(r"\b4k\b", re.IGNORECASE)),
    ("2K", re.compile(r"\b2k\b", re.IGNORECASE)),
    ("UHD", re.compile(r"\buhd\b", re.IGNORECASE)),
    ("FHD", re.compile(r"\bfhd\b", re.IGNORECASE)),
    ("HD", re.compile(r"\bhd\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_resolution(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    result = _first_match(text, _RESOLUTION_PATTERNS)
    if result != "Unknown":
        return result

    try:
        match = _RE_DIMENSIONS.search(text)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            if width >= 7000 and height >= 3500:
                return "4320p"
            if width >= 3500 and height >= 1800:
                return "2160p"
            if width >= 2400 and height >= 1200:
                return "1440p"
            if width >= 1800 and height >= 950:
                return "1080p"
            if width >= 1100 and height >= 650:
                return "720p"
            if width >= 600 and height >= 350:
                return "SD"
    except (TypeError, ValueError):
        pass

    return "Unknown"

# ============================================================
# LANGUAGE DETECTOR
# ============================================================

_LANGUAGE_PATTERNS_COMPILED = {
    "Telugu": [
        re.compile(r"\btelugu\b", re.IGNORECASE),
        re.compile(r"\btelu\b", re.IGNORECASE),
        re.compile(r"\btelegu\b", re.IGNORECASE),
        re.compile(r"\btel\b", re.IGNORECASE),
        re.compile(r"\btlg\b", re.IGNORECASE),
        re.compile(r"\bte\b(?=\s+(?:audio|dubbed|dub|org|original))", re.IGNORECASE),
        re.compile(r"\bte\s*-\s*(?:audio|dubbed|dub)\b", re.IGNORECASE),
    ],
    "Hindi": [
        re.compile(r"\bhindi\b", re.IGNORECASE),
        re.compile(r"\bhind\b", re.IGNORECASE),
        re.compile(r"\bhin\b", re.IGNORECASE),
        re.compile(r"\bhi\b(?=\s+(?:audio|dubbed|dub|org|original))", re.IGNORECASE),
        re.compile(r"\bbollywood\b", re.IGNORECASE),
    ],
    "Tamil": [
        re.compile(r"\btamil\b", re.IGNORECASE),
        re.compile(r"\btam\b", re.IGNORECASE),
        re.compile(r"\btam\b(?=\s+(?:audio|dubbed|dub))", re.IGNORECASE),
        re.compile(r"\bta\b(?=\s+(?:audio|dubbed|dub|org|original))", re.IGNORECASE),
    ],
    "Malayalam": [
        re.compile(r"\bmalayalam\b", re.IGNORECASE),
        re.compile(r"\bmal\b", re.IGNORECASE),
        re.compile(r"\bmallu\b", re.IGNORECASE),
        re.compile(r"\bml\b(?=\s+(?:audio|dubbed|dub|org|original))", re.IGNORECASE),
    ],
    "Kannada": [
        re.compile(r"\bkannada\b", re.IGNORECASE),
        re.compile(r"\bkan\b", re.IGNORECASE),
        re.compile(r"\bkann\b", re.IGNORECASE),
        re.compile(r"\bkn\b(?=\s+(?:audio|dubbed|dub|org|original))", re.IGNORECASE),
    ],
    "English": [
        re.compile(r"\benglish\b", re.IGNORECASE),
        re.compile(r"\beng\b", re.IGNORECASE),
        re.compile(r"\boriginal\s+audio\b", re.IGNORECASE),
    ],
}

_LANG_CODES = {
    "Telugu": ["te", "tel", "tlg"],
    "Hindi": ["hi", "hin"],
    "Tamil": ["ta", "tam"],
    "Malayalam": ["ml", "mal"],
    "Kannada": ["kn", "kan"],
    "English": ["en", "eng"],
}

_LANG_CODE_PATTERNS = {}
_CTX_FOLLOWING = r"(?:\s+(?:audio|dubbed|dub|language|lang|subs?|subtitle|org|original))"
_CTX_PRECEDING = r"(?:audio|dubbed|dub|language|lang|subs?|subtitle|org|original)\s+"

for _lang, _codes in _LANG_CODES.items():
    _LANG_CODE_PATTERNS[_lang] = []
    for _c in _codes:
        c_esc = re.escape(_c)
        _LANG_CODE_PATTERNS[_lang].append([
            re.compile(rf"(?<!\w){c_esc}(?!\w){_CTX_FOLLOWING}", re.IGNORECASE),
            re.compile(rf"{_CTX_PRECEDING}{c_esc}(?!\w)", re.IGNORECASE),
            re.compile(rf"(?<!\w){c_esc}(?!\w)", re.IGNORECASE),
        ])

@lru_cache(maxsize=8192)
def detect_language_codes(name: str):
    if not name:
        return []

    text = _normalized_lower(name)
    if not text:
        return []

    found = []
    for language, pattern_groups in _LANG_CODE_PATTERNS.items():
        for group in pattern_groups:
            matched = False
            for pat in group:
                if pat.search(text):
                    matched = True
                    break
            if matched:
                found.append(language)
                break

    return _dedupe(found)

@lru_cache(maxsize=8192)
def _detect_languages_tuple(name: str):
    if not name:
        return ("Unknown",)

    text = _normalized_lower(name)
    if not text:
        return ("Unknown",)

    found = []
    for language, patterns in _LANGUAGE_PATTERNS_COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                found.append(language)
                break

    for language in detect_language_codes(name):
        if language not in found:
            found.append(language)

    if _RE_DUAL_AUDIO.search(text) or _RE_MULTI_AUDIO.search(text):
        if "English" not in found:
            found.append("English")

    found = _dedupe(found)
    return tuple(found) if found else ("Unknown",)

def detect_languages(name: str):
    return list(_detect_languages_tuple(name))

def detect_language(name: str):
    languages = detect_languages(name)
    if not languages or languages == ["Unknown"]:
        return "Unknown"
    return " + ".join(languages)

# ============================================================
# AUDIO DETECTOR
# ============================================================

_AUDIO_PATTERNS = [
    ("TRUEHD ATMOS", re.compile(r"\btruehd\s+atmos\b", re.IGNORECASE)),
    ("DOLBY ATMOS", re.compile(r"\bdolby\s+atmos\b", re.IGNORECASE)),
    ("ATMOS", re.compile(r"\batmos\b", re.IGNORECASE)),
    ("TRUEHD", re.compile(r"\btruehd\b", re.IGNORECASE)),
    ("DTS-HD MA", re.compile(r"\bdts\s+hd\s+ma\b|\bdts\s+hd\s+master\s+audio\b", re.IGNORECASE)),
    ("DTS-HD", re.compile(r"\bdts\s+hd\b", re.IGNORECASE)),
    ("DTS-X", re.compile(r"\bdts\s+x\b|\bdtsx\b", re.IGNORECASE)),
    ("DTS", re.compile(r"\bdts\b", re.IGNORECASE)),
    ("DOLBY DIGITAL PLUS", re.compile(r"\bdolby\s+digital\s+plus\b", re.IGNORECASE)),
    ("DOLBY DIGITAL", re.compile(r"\bdolby\s+digital\b", re.IGNORECASE)),
    ("EAC3", re.compile(r"\be[\s-]*ac3\b|\beac3\b", re.IGNORECASE)),
    ("DDP", re.compile(r"\bddp\b|\bdd\s*\+", re.IGNORECASE)),
    ("AC3", re.compile(r"\bac3\b", re.IGNORECASE)),
    ("AAC", re.compile(r"\baac\b", re.IGNORECASE)),
    ("FLAC", re.compile(r"\bflac\b", re.IGNORECASE)),
    ("OPUS", re.compile(r"\bopus\b", re.IGNORECASE)),
    ("MP3", re.compile(r"\bmp3\b", re.IGNORECASE)),
    ("PCM", re.compile(r"\bpcm\b", re.IGNORECASE)),
]

_CHANNEL_PATTERNS = [
    ("7.1", re.compile(r"(?<![\d.])7\s*[._]?\s*1(?![\d.])")),
    ("6.1", re.compile(r"(?<![\d.])6\s*[._]?\s*1(?![\d.])")),
    ("5.1", re.compile(r"(?<![\d.])5\s*[._]?\s*1(?![\d.])")),
    ("2.1", re.compile(r"(?<![\d.])2\s*[._]?\s*1(?![\d.])")),
    ("2.0", re.compile(r"(?<![\d.])2\s*[._]?\s*0(?![\d.])")),
]

_COMPACT_CHANNEL_PATTERNS = [
    ("7.1", re.compile(r"(?<!\d)7\s+1(?!\d)")),
    ("6.1", re.compile(r"(?<!\d)6\s+1(?!\d)")),
    ("5.1", re.compile(r"(?<!\d)5\s+1(?!\d)")),
    ("2.1", re.compile(r"(?<!\d)2\s+1(?!\d)")),
    ("2.0", re.compile(r"(?<!\d)2\s+0(?!\d)")),
]

@lru_cache(maxsize=8192)
def detect_channels(name: str):
    if not name:
        return "Unknown"

    text = _text(name).lower()
    if not text:
        return "Unknown"

    for label, pattern in _CHANNEL_PATTERNS:
        if pattern.search(text):
            return label

    for label, pattern in _COMPACT_CHANNEL_PATTERNS:
        if pattern.search(text):
            return label

    return "Unknown"

@lru_cache(maxsize=8192)
def detect_audio(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    primary = _first_match(text, _AUDIO_PATTERNS)
    channel = detect_channels(name)

    if primary == "Unknown":
        return channel if channel != "Unknown" else "Unknown"

    if channel != "Unknown":
        if primary not in ("DOLBY ATMOS", "ATMOS", "TRUEHD ATMOS"):
            return f"{primary} {channel}"

    return primary

# ============================================================
# SOURCE DETECTOR
# ============================================================

_SOURCE_PATTERNS = [
    ("WEB-DL", re.compile(r"\bweb\s*dl\b", re.IGNORECASE)),
    ("WEBRip", re.compile(r"\bweb\s*rip\b", re.IGNORECASE)),
    ("WEBHD", re.compile(r"\bwebhd\b", re.IGNORECASE)),
    ("AMZN", re.compile(r"\bamzn\b|\bamazon\b", re.IGNORECASE)),
    ("NF", re.compile(r"\bnf\b|\bnetflix\b", re.IGNORECASE)),
    ("DSNP", re.compile(r"\bdsnp\b|\bdisney\s*(?:plus|\+)\b", re.IGNORECASE)),
    ("HMAX", re.compile(r"\bhmax\b|\bhbo\s*max\b", re.IGNORECASE)),
    ("ATVP", re.compile(r"\batvp\b|\bapple\s*tv(?:\s*\+)?\b", re.IGNORECASE)),
    ("PCOK", re.compile(r"\bpcok\b|\bpeacock\b", re.IGNORECASE)),
    ("HULU", re.compile(r"\bhulu\b", re.IGNORECASE)),
    ("ZEE5", re.compile(r"\bzee5\b", re.IGNORECASE)),
    ("JIOCINEMA", re.compile(r"\bjio\s*cinema\b|\bjiocinema\b", re.IGNORECASE)),
    ("HOTSTAR", re.compile(r"\bhotstar\b", re.IGNORECASE)),
    ("SONYLIV", re.compile(r"\bsony\s*liv\b|\bsonyliv\b", re.IGNORECASE)),
    ("AHA", re.compile(r"\baha\b", re.IGNORECASE)),
    ("UHD BluRay", re.compile(r"\buhd\s*bluray\b|\buhd\s*blu\s*ray\b|\b4k\s*bluray\b|\b4k\s*blu\s*ray\b", re.IGNORECASE)),
    ("BDRemux", re.compile(r"\bbd\s*remux\b|\bbluray\s*remux\b|\bblu\s*ray\s*remux\b", re.IGNORECASE)),
    ("BluRay", re.compile(r"\bbluray\b|\bblu\s*ray\b", re.IGNORECASE)),
    ("BDRip", re.compile(r"\bbd\s*rip\b", re.IGNORECASE)),
    ("BRRip", re.compile(r"\bbr\s*rip\b", re.IGNORECASE)),
    ("REMUX", re.compile(r"\bremux\b", re.IGNORECASE)),
    ("DVDRip", re.compile(r"\bdvd\s*rip\b", re.IGNORECASE)),
    ("DVD", re.compile(r"\bdvd\b", re.IGNORECASE)),
    ("HDTVRip", re.compile(r"\bhdtv\s*rip\b", re.IGNORECASE)),
    ("HDTV", re.compile(r"\bhdtv\b", re.IGNORECASE)),
    ("TVRip", re.compile(r"\btv\s*rip\b", re.IGNORECASE)),
    ("CAM", re.compile(r"\bhd\s*cam\b|\bhq\s*cam\b|\bcam\b", re.IGNORECASE)),
    ("TS", re.compile(r"\btele\s*sync\b|\btelesync\b|\bts\b", re.IGNORECASE)),
    ("TC", re.compile(r"\btele\s*cine\b|\btelecine\b|\btc\b", re.IGNORECASE)),
    ("SCR", re.compile(r"\bscreener\b|\bscr\b", re.IGNORECASE)),
    ("WORKPRINT", re.compile(r"\bwork\s*print\b|\bworkprint\b", re.IGNORECASE)),
    ("WEB", re.compile(r"\bweb\b", re.IGNORECASE)),
]
_RE_WEB_FALLBACK = re.compile(r"\bweb\b", re.IGNORECASE)

@lru_cache(maxsize=8192)
def detect_source(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    result = _first_match(text, _SOURCE_PATTERNS)
    if result != "Unknown":
        return result

    if _RE_WEB_FALLBACK.search(text):
        return "WEB"

    return "Unknown"

# ============================================================
# VIDEO CODEC DETECTOR
# ============================================================

_CODEC_PATTERNS = [
    ("H.266", re.compile(r"\bh\s*266\b|\bh266\b|\bvvc\b", re.IGNORECASE)),
    ("AV1", re.compile(r"\bav1\b", re.IGNORECASE)),
    ("VP9", re.compile(r"\bvp9\b", re.IGNORECASE)),
    ("VP8", re.compile(r"\bvp8\b", re.IGNORECASE)),
    ("H.265", re.compile(r"\bh\s*265\b|\bh265\b|\bhevc\b|\bx265\b|\bhvc1\b", re.IGNORECASE)),
    ("H.264", re.compile(r"\bh\s*264\b|\bh264\b|\bavc\b|\bx264\b", re.IGNORECASE)),
    ("MPEG-4", re.compile(r"\bmpeg\s*4\b|\bmp4v\b", re.IGNORECASE)),
    ("MPEG-2", re.compile(r"\bmpeg\s*2\b", re.IGNORECASE)),
    ("XviD", re.compile(r"\bxvid\b", re.IGNORECASE)),
    ("DivX", re.compile(r"\bdivx\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_video_codec(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _CODEC_PATTERNS) if text else "Unknown"

# ============================================================
# HDR DETECTOR
# ============================================================

_HDR_PATTERNS = [
    ("Dolby Vision + HDR10+", re.compile(r"(?=.*\bdolby\s*vision\b)(?=.*\bhdr\s*10\s*(?:\+|plus)\b)", re.IGNORECASE)),
    ("Dolby Vision + HDR10", re.compile(r"(?=.*\bdolby\s*vision\b)(?=.*\bhdr\s*10\b)", re.IGNORECASE)),
    ("Dolby Vision", re.compile(r"\bdolby\s*vision\b|\bdolbyvision\b|\bdv\b", re.IGNORECASE)),
    ("HDR10+", re.compile(r"\bhdr\s*10\s*(?:\+|plus)\b|\bhdr10plus\b", re.IGNORECASE)),
    ("HDR10", re.compile(r"\bhdr\s*10\b", re.IGNORECASE)),
    ("HLG", re.compile(r"\bhlg\b", re.IGNORECASE)),
    ("HDR", re.compile(r"\bhdr\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_hdr(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _HDR_PATTERNS) if text else "Unknown"

# ============================================================
# VIDEO BIT DEPTH DETECTOR
# ============================================================

_BIT_DEPTH_PATTERNS = [
    ("12-bit", re.compile(r"\b12\s*bit\b|\b12bit\b", re.IGNORECASE)),
    ("10-bit", re.compile(r"\b10\s*bit\b|\b10bit\b", re.IGNORECASE)),
    ("8-bit", re.compile(r"\b8\s*bit\b|\b8bit\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_bit_depth(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _BIT_DEPTH_PATTERNS) if text else "Unknown"

# ============================================================
# SCAN TYPE DETECTOR
# ============================================================

_RE_INTERLACED = re.compile(r"\binterlaced\b", re.IGNORECASE)
_RE_PROGRESSIVE = re.compile(r"\bprogressive\b", re.IGNORECASE)
_RE_SCAN_I = re.compile(r"(?<!\d)\d{3,4}i\b", re.IGNORECASE)
_RE_SCAN_P = re.compile(r"(?<!\d)\d{3,4}p\b", re.IGNORECASE)

@lru_cache(maxsize=8192)
def detect_scan_type(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    if _RE_INTERLACED.search(text):
        return "Interlaced"
    if _RE_PROGRESSIVE.search(text):
        return "Progressive"
    if _RE_SCAN_I.search(text):
        return "Interlaced"
    if _RE_SCAN_P.search(text):
        return "Progressive"

    return "Unknown"

# ============================================================
# FPS DETECTOR
# ============================================================

_FPS_PATTERNS = [
    ("59.94 FPS", re.compile(r"(?<![\d.])59[\s._]*94\s*fps\b", re.IGNORECASE)),
    ("29.97 FPS", re.compile(r"(?<![\d.])29[\s._]*97\s*fps\b", re.IGNORECASE)),
    ("23.976 FPS", re.compile(r"(?<![\d.])23[\s._]*976\s*fps\b", re.IGNORECASE)),
    ("60 FPS", re.compile(r"(?<![\d.])60\s*fps\b", re.IGNORECASE)),
    ("50 FPS", re.compile(r"(?<![\d.])50\s*fps\b", re.IGNORECASE)),
    ("30 FPS", re.compile(r"(?<![\d.])30\s*fps\b", re.IGNORECASE)),
    ("25 FPS", re.compile(r"(?<![\d.])25\s*fps\b", re.IGNORECASE)),
    ("24 FPS", re.compile(r"(?<![\d.])24\s*fps\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_fps(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _FPS_PATTERNS) if text else "Unknown"

# ============================================================
# ASPECT RATIO DETECTOR
# ============================================================

_ASPECT_PATTERNS = [
    ("2.40:1", re.compile(r"(?<!\d)2[\s._]*40\s*[:x]\s*1\b", re.IGNORECASE)),
    ("2.39:1", re.compile(r"(?<!\d)2[\s._]*39\s*[:x]\s*1\b", re.IGNORECASE)),
    ("2.35:1", re.compile(r"(?<!\d)2[\s._]*35\s*[:x]\s*1\b", re.IGNORECASE)),
    ("1.85:1", re.compile(r"(?<!\d)1[\s._]*85\s*[:x]\s*1\b", re.IGNORECASE)),
    ("16:9", re.compile(r"(?<!\d)16\s*[:x]\s*9\b", re.IGNORECASE)),
    ("4:3", re.compile(r"(?<!\d)4\s*[:x]\s*3\b", re.IGNORECASE)),
    ("1:1", re.compile(r"(?<!\d)1\s*[:x]\s*1\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_aspect_ratio(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _ASPECT_PATTERNS) if text else "Unknown"

# ============================================================
# EDITION DETECTOR
# ============================================================

_EDITION_PATTERNS = [
    ("Director's Cut", re.compile(r"\bdirector\s*['’]?\s*s\s*cut\b|\bdirectors\s*cut\b", re.IGNORECASE)),
    ("Extended Cut", re.compile(r"\bextended\s*cut\b", re.IGNORECASE)),
    ("Extended Edition", re.compile(r"\bextended\s*edition\b", re.IGNORECASE)),
    ("Unrated", re.compile(r"\bunrated\b", re.IGNORECASE)),
    ("Uncut", re.compile(r"\buncut\b", re.IGNORECASE)),
    ("Remastered", re.compile(r"\bremastered\b", re.IGNORECASE)),
    ("Restored", re.compile(r"\brestored\b", re.IGNORECASE)),
    ("Anniversary Edition", re.compile(r"\banniversary\s*edition\b", re.IGNORECASE)),
    ("Collector's Edition", re.compile(r"\bcollector\s*['’]?\s*s\s*edition\b", re.IGNORECASE)),
    ("Special Edition", re.compile(r"\bspecial\s*edition\b", re.IGNORECASE)),
    ("Ultimate Edition", re.compile(r"\bultimate\s*edition\b", re.IGNORECASE)),
    ("IMAX", re.compile(r"\bimax\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_edition(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    found = _all_matches(text, _EDITION_PATTERNS)
    return ", ".join(found) if found else "Unknown"

# ============================================================
# RELEASE TYPE DETECTOR
# ============================================================

_RELEASE_TYPE_PATTERNS = [
    ("WEB-DL", re.compile(r"\bweb\s*dl\b", re.IGNORECASE)),
    ("WEBRip", re.compile(r"\bweb\s*rip\b", re.IGNORECASE)),
    ("UHD BluRay", re.compile(r"\buhd\s*bluray\b|\buhd\s*blu\s*ray\b|\b4k\s*bluray\b|\b4k\s*blu\s*ray\b", re.IGNORECASE)),
    ("BDRemux", re.compile(r"\bbd\s*remux\b|\bbluray\s*remux\b|\bblu\s*ray\s*remux\b", re.IGNORECASE)),
    ("BluRay", re.compile(r"\bbluray\b|\bblu\s*ray\b", re.IGNORECASE)),
    ("Remux", re.compile(r"\bremux\b", re.IGNORECASE)),
    ("BDRip", re.compile(r"\bbd\s*rip\b", re.IGNORECASE)),
    ("BRRip", re.compile(r"\bbr\s*rip\b", re.IGNORECASE)),
    ("DVDRip", re.compile(r"\bdvd\s*rip\b", re.IGNORECASE)),
    ("DVD", re.compile(r"\bdvd\b", re.IGNORECASE)),
    ("HDTVRip", re.compile(r"\bhdtv\s*rip\b", re.IGNORECASE)),
    ("HDTV", re.compile(r"\bhdtv\b", re.IGNORECASE)),
    ("TVRip", re.compile(r"\btv\s*rip\b", re.IGNORECASE)),
    ("CAM", re.compile(r"\bhd\s*cam\b|\bhq\s*cam\b|\bcam\b", re.IGNORECASE)),
    ("TS", re.compile(r"\btele\s*sync\b|\btelesync\b|\bts\b", re.IGNORECASE)),
    ("TC", re.compile(r"\btele\s*cine\b|\btelecine\b|\btc\b", re.IGNORECASE)),
    ("SCR", re.compile(r"\bscreener\b|\bscr\b", re.IGNORECASE)),
    ("WORKPRINT", re.compile(r"\bwork\s*print\b|\bworkprint\b", re.IGNORECASE)),
    ("WEB", re.compile(r"\bweb\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_release_type(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _RELEASE_TYPE_PATTERNS) if text else "Unknown"

# ============================================================
# SUBTITLE DETECTOR
# ============================================================

_SUBTITLE_PATTERNS = [
    ("English Subtitles", re.compile(r"\besubs?\b|\benglish\s*subs?\b|\benglish\s*subtitles?\b", re.IGNORECASE)),
    ("Subtitles", re.compile(r"\bsubtitles?\b|\bsubs?\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_subtitles(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _SUBTITLE_PATTERNS) if text else "Unknown"

# ============================================================
# DUAL / MULTI AUDIO DETECTOR
# ============================================================

@lru_cache(maxsize=8192)
def detect_audio_type(name: str):
    if not name:
        return "Unknown"

    text = _normalized_lower(name)
    if not text:
        return "Unknown"

    if _RE_DUAL_AUDIO.search(text):
        return "Dual Audio"

    if _RE_MULTI_AUDIO.search(text):
        return "Multi Audio"

    return "Unknown"

# ============================================================
# CONTAINER DETECTOR
# ============================================================

_CONTAINER_PATTERNS = [
    ("MKV", re.compile(r"\bmkv\b|\bmatroska\b", re.IGNORECASE)),
    ("MP4", re.compile(r"\bmp4\b", re.IGNORECASE)),
    ("AVI", re.compile(r"\bavi\b", re.IGNORECASE)),
    ("MOV", re.compile(r"\bmov\b", re.IGNORECASE)),
    ("MPEG", re.compile(r"\bmpeg\b", re.IGNORECASE)),
    ("TS", re.compile(r"\bm2ts\b|\btransport\s*stream\b", re.IGNORECASE)),
    ("WEBM", re.compile(r"\bwebm\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_container(name: str):
    if not name:
        return "Unknown"
    text = _normalized_lower(name)
    return _first_match(text, _CONTAINER_PATTERNS) if text else "Unknown"

# ============================================================
# FILE SIZE DETECTOR
# ============================================================

@lru_cache(maxsize=8192)
def detect_file_size(name: str):
    if not name:
        return "Unknown"

    text = _text(name)
    match = _RE_FILE_SIZE.search(text)
    if not match:
        return "Unknown"

    return f"{match.group(1)} {match.group(2).upper()}"

# ============================================================
# RELEASE FLAGS DETECTOR
# ============================================================

_RELEASE_FLAG_PATTERNS = [
    ("Uncut", re.compile(r"\buncut\b", re.IGNORECASE)),
    ("Extended", re.compile(r"\bextended\b", re.IGNORECASE)),
    ("IMAX", re.compile(r"\bimax\b", re.IGNORECASE)),
    ("Hybrid", re.compile(r"\bhybrid\b", re.IGNORECASE)),
    ("Remastered", re.compile(r"\bremastered\b", re.IGNORECASE)),
    ("Repack", re.compile(r"\brepack\b", re.IGNORECASE)),
    ("Proper", re.compile(r"\bproper\b", re.IGNORECASE)),
    ("Complete", re.compile(r"\bcomplete\b", re.IGNORECASE)),
    ("Original", re.compile(r"\boriginal\b", re.IGNORECASE)),
    ("Theatrical", re.compile(r"\btheatrical\b", re.IGNORECASE)),
    ("Unrated", re.compile(r"\bunrated\b", re.IGNORECASE)),
]

@lru_cache(maxsize=8192)
def detect_release_flags(name: str):
    if not name:
        return []
    text = _normalized_lower(name)
    return _all_matches(text, _RELEASE_FLAG_PATTERNS) if text else []

# ============================================================
# MASTER DETECTION
# ============================================================

def detect_all(name: str):
    text = _text(name)
    if not text:
        return {
            "year": "Unknown",
            "quality": "Unknown",
            "languages": ["Unknown"],
            "language": "Unknown",
            "audio": "Unknown",
            "audio_type": "Unknown",
            "channels": "Unknown",
            "source": "Unknown",
            "release_type": "Unknown",
            "video_codec": "Unknown",
            "hdr": "Unknown",
            "bit_depth": "Unknown",
            "scan_type": "Unknown",
            "fps": "Unknown",
            "resolution": "Unknown",
            "aspect_ratio": "Unknown",
            "edition": "Unknown",
            "subtitles": "Unknown",
            "container": "Unknown",
            "file_size": "Unknown",
            "language_codes": [],
            "release_flags": [],
        }

    languages = detect_languages(text)

    return {
        "year": detect_year(text),
        "quality": detect_quality(text),
        "languages": languages,
        "language": detect_language(text),
        "audio": detect_audio(text),
        "audio_type": detect_audio_type(text),
        "channels": detect_channels(text),
        "source": detect_source(text),
        "release_type": detect_release_type(text),
        "video_codec": detect_video_codec(text),
        "hdr": detect_hdr(text),
        "bit_depth": detect_bit_depth(text),
        "scan_type": detect_scan_type(text),
        "fps": detect_fps(text),
        "resolution": detect_resolution(text),
        "aspect_ratio": detect_aspect_ratio(text),
        "edition": detect_edition(text),
        "subtitles": detect_subtitles(text),
        "container": detect_container(text),
        "file_size": detect_file_size(text),
        "language_codes": detect_language_codes(text),
        "release_flags": detect_release_flags(text),
    }

# ============================================================
# END OF DETECTORS.PY
# ============================================================
