import re
from functools import lru_cache

# ============================================================
# PREFIX / SOURCE CLEANING
# ============================================================

UNWANTED_PREFIXES = [
    "@VGCinemas_off",
    "{} ",
    "{_} ",
    "mj ",
    "mj",
    "www_Tamilblasters_vin_",
    "www_Tamilblasters_vin",
    "www_Tamilblasters_vin -",
    "www_Tamilblasters_vin- ",
    "www_Tamilblasters_vin-",
    "www_Tamilblasters_vin",
    "www_Tamilblasters_vin ",
    "@Hollywoodtelugufiles_",
    "@Hollywoodtelugufiles",
    "@Hollywoodtelugufiles- ",
    "@Hollywoodtelugufiles-- ",
    "@Hollywoodtelugufiles -",
    "@Hollywoodtelugufiles - ",
    "@Hollywoodtelu_",
    "@Hollywoodtelu -",
    "@Hollywoodtelu_ ",
    "@Hollywoodtelu- ",
    "@Hollywoodtelu - ",
    "@Hollywoodtelu",
    "@Hollywoodtelu ",
    "@Official_HDL - ",
    "@Official_HDL -",
    "@Official_HDL_",
    "@Official_HDL -- ",
    "@Official_HDL ",
    "@Official_HDL",
    "@Askmetelugu1 ",
    "@Askmetelugu1 - ",
    "@Askmetelugu1 -",
    "@Askmetelugu1_",
    "@DevHEVC_",
    "@DevHEVC - ",
    "@DevHEVC -",
    "@DevHEVC ",
    "@DevHEVC",
    "w.1TamilBlasters.gold - ",
    "w.1TamilBlasters.gold -",
    "w.1TamilBlasters.gold ",
    "w.1TamilBlasters.gold",
    "@AM_linkzz`",
    "@Malli4U_Official2 - ",
    "@Malli4U_Official2 -",
    "@Malli4U_Official2_",
    "@Malli4U_Official2 ",
    "@Malli4U_Official2-",
    "@Malli4U_Official2",
    "-Malli4U_Official2",
    "Malli4U_Official2",
    "MWK_",
    "MWK",
    "MWK - ",
    "MWK -",
    "MWK-",
    "@SKMOVIEDD",
    "@SKMOVIEDD_",
    "@SKMOVIEDD - ",
    "@SKMOVIEDD -",
    "@SKMOVIEDD ",
    "@MOVIESXYZ_OFCL - ",
    "@MOVIESXYZ_OFCL -",
    "@MOVIESXYZ_OFCL ",
    "@MOVIESXYZ_OFCL_",
    "@MOVIESXYZ_OFCL",
    "@Hollywoodmoviesleaker1 -",
    "@Hollywoodmoviesleaker1 - ",
    "@Hollywoodmoviesleaker1_",
    "@Hollywoodmoviesleaker1",
    "@Hollywoodmoviesleaker1 ",
    "@Raja_Rewrite -",
    "@Raja_Rewrite - ",
    "@Raja_Rewrite_",
    "@Raja_Rewrite ",
    "@Raja_Rewrite",
    "@Rocerz_2K",
    "@Rocerz_2K ",
    "@Rocerz_2K - ",
    "@Rocerz_2K -",
    "@Rocerz_2K- ",
    "@Rocerz_2K_",
    "www.1TamilBlasters.tel",
    "www.1TamilMV.boo -",
    "www.1TamilMV.boo - ",
    "www.1TamilMV.boo_",
    "www.1TamilMV.boo",
    "www.1TamilMV.boo ",
    "HollywoodGbs_",
    "@HollywoodGbs_",
    "[TF]",
    "@ViewCinemas_",
    "@ViewCinemas",
    "@ViewCinemas - - -",
    "@WayneEntertainment - ",
    "@WayneEntertainment_",
    "@WayneEntertainment ",
    "@WaynEntertainment - ",
    "@WaynEntertainment",
    "@Gangz7 - ",
    "@Gangz7 ",
    "@Gangz7",
    "@Gangz7_",
    "@PrakyTV - ",
    "@PrakyTV -",
    "@PrakyTV",
    "@PrakyTV ",
    "@PH_FILES",
    "@NaChannel4 -",
    "@NaChannel4 - ",
    "@NaChannel4 - - ",
    "@NaChannel4 -- ",
    "@NaChannel4 - -",
    "@Twister_Originals - ",
    "@Twister_Originals -",
    "@Twister_Originals ",
    "@Twister_Originals_",
    "@Twister_Originals",
    "@TollyMovies_Official -",
    "@TollyMovies_Official - ",
    "@HollyMovies4_",
    "@HollyMovies4_ ",
    "@HollyMovies4 - ",
    "@HollyMovies4",
    "@TGCinemaworld -",
    "@TGCinemaworld - ",
    "@TGCinemaworld_",
    "@TGCinemaworld",
    "@Telugu_bomma_Moviez",
    "@Telugu_bomma_Moviez ",
    "@Telugu_bomma_Moviez - ",
    "@Telugu_bomma_Moviez_",
    "@Telugu_bomma_Moviez -",
    "@Telugu_Moviez_Addaa18- ",
    "@Telugu_Moviez_Addaa18 - ",
    "@Telugu_Moviez_Addaa18_",
    "@Telugu_Moviez_Addaa18",
    "@Telugudubbing_movies_",
    "@Telugudubbing_movies_ ",
    "@Telugudubbing_movies - ",
    "@Telugudubbing_movies -",
    "@Telugudubbing_movies",
    "@Telugu_tigers -",
    "@Telugu_tigers - ",
    "@Telugu_tigers- ",
    "@Telugu_tigers_",
    "@Telugu_tigers",
    "@Telugu_tigers ",
    "@TeluguZoneOFC",
    "@TeluguZoneOFC ",
    "@TeluguZoneOFC - ",
    "@TeluguZoneOFC -- ",
    "@Enjoypandugow -",
    "@Enjoypandugow - ",
    "@Enjoypandugow",
    "@Enjoypandugow ",
    "@Central_Links - ",
    "@Central_Links ",
    "@Central_Links -",
    "[TorrentCouch.com].",
    "[TorrentCouch.com]. ",
    "[TorrentCouch.com]",
    "@HiBomma - ",
    "@HiBomma -",
    "@HiBomma ",
    "@Alightmovies4u - ",
    "@Alightmovies4u -",
    "@Alightmovies4u_",
    "@Alightmovies4u ",
    "@Alightmovies4u",
    "@Alightmovies4u -Copy of [Part 1] ",
    "@Alightmovies4u -Copy of [Part 1]",
    "@ALIGHTMOVIES4U - ",
    "@ALIGHTMOVIES4U -",
    "@ALIGHTMOVIES4U ",
    "@ALIGHTMOVIES4U_",
    "@ALIGHTMOVIES4U",
    "@kolipaka_arun - - ",
    "@kolipaka_arun - ",
    "@kolipaka_arun -",
    "@kolipaka_arun_",
    "@kolipaka_arun",
    "@kolipaka_arun ",
    "@TeluguMoviesXpress - ",
    "@TeluguMoviesXpress -",
    "@TeluguMoviesXpress_",
    "@TeluguMoviesXpress ",
    "[@MOVIES_HUNT]",
    "@TBOriginals_",
    "@CINEMA_BEACON",
    "@CV",
    "HollywoodGbs - ",
    "HollywoodGbs -",
    "HollywoodGbs",
    "@Movies_arena_4u_",
    "@TG_Movies4u ",
    "@TG_Movies4u_",
    "@TG_Movies4u - ",
    "@TG_Movies4u  - ",
    "@TG_Movies4u  -",
    "@TG_Movies - ",
    "@TG_Movies -",
    "@TG_Movies4u -",
    "@Tg_Movies4u --",
    "@TG_Movies4u -- ",
    "@Tg_Movies4u - ",
    "@Tg_Movies4u -- ",
    "@tg_movies4u - ",
    "@TG_Movies4u-",
    "TG_Movies4u-",
    "@CR7XPRAJITH ",
    "@CR7XPRAJITH  ",
    "@CR7XPRAJITH",
    "[FC]",
    "@PrankyTv",
    "@MJ_Linkz",
    "@MM_X265",
    "@TroopOriginals_",
    "@VGCINEMAS_",
    "@VGCINEMAS",
    "_@VGCINEMAS2_",
    "@VGCinemas_ofcl_",
    "@VGCinemas_Ofcl",
    "@telugu_moviez_",
    "@Filmyzone4u_",
    "@NDLMoviee_",
    "@KumarValimaiofcl_",
    "@S95Hub",
    "@S95files_",
    "@S95files - ",
    "@MnA_Movies_",
    "@WayneEntertainment",
    "@MULTIVERSE_OFCL",
    "@MULTIVERSE_OFCL -- ",
    "@MULTIVERSE_OFCL - - ",
    "@NDLMoviez_",
    "@NDLMoviez - ",
    "@NDLMoviez -",
    "@NDLMoviez ",
    "mj_link_4u_",
    "mj_link_4u",
    "@SGCINEMAS",
    "@mj_link_4u_",
    "@mj_link_4u",
    "mj_links_2u_",
    "mj_links_2u - ",
    "mj_links_2u -",
    "mj_links_2u ",
    "mj_link_2u_",
    "mj_link_2u- ",
    "mj_link_2u - ",
    "mj_link_2u -",
    "mj_link_2u",
    "mj_link_2u ",
    "TollyNexus_",
    "TeluguFlixx_",
    "AMxMJ_",
    "@TR_MINI - ",
    "@TR_MINI -",
    "@TR_MINI ",
    "@TR_MINI_",
    "[CF]",
    "@CC_X265",
    "_mx_",
    "www_3MovieRulz_mx_",
    "@toonflexpage - ",
    "@toonflexpage",
    "toonflex - ",
    "toonflex",
    "Toonfelx - ",
    "Toonflex",
    "@Anu_movies_",
    "@Anu_movies - ",
    "@Anu_movies",
    "@TrollerMawaofficial_",
    "@MM_",
    "[MP]",
    "[D&O]",
    "[D&O].",
    "@",
]

# ============================================================
# PRE-COMPILED COMBINED PREFIX REGEX (ULTRA-FAST SINGLE PASS)
# ============================================================

_SORTED_PREFIXES = sorted(UNWANTED_PREFIXES, key=len, reverse=True)
_PREFIX_REGEX_STR = r"^\s*(?:" + "|".join(re.escape(p) for p in _SORTED_PREFIXES) + r")(?:\s*(?:[-_.:|]+)\s*|\s+)?"
_RE_COMBINED_PREFIX = re.compile(_PREFIX_REGEX_STR, re.IGNORECASE)

# ============================================================
# URL / LINK / USERNAME REGEX
# ============================================================

_WEB_URL = re.compile(r"(?i)(?:https?://|ftp://)[^\s]+")
_WWW_URL = re.compile(r"(?i)\bwww\.[^\s]+")
_TELEGRAM_LINK = re.compile(r"(?i)\b(?:t\.me|telegram\.me|telegram\.dog)/[^\s]+")
_URL_LABEL = re.compile(r"(?i)\b(?:url|urls|link|links)\s*[:=\-–—|]\s*")
_TELEGRAM_USERNAME = re.compile(r"@[A-Za-z0-9_]{3,}")

_RE_SPACES = re.compile(r"[ \t]+")
_RE_SPACE_EXT = re.compile(r"[ \t]+\.(?=[A-Za-z0-9]{1,8}$)")
_RE_TRAILING_SEP_EXT = re.compile(r"[ \t]*[-_.:|]+[ \t]*(\.[A-Za-z0-9]{1,8})$")
_RE_REPEATED_SPACES = re.compile(r"[ \t]{2,}")
_RE_VIDEO_EXT = re.compile(r"\.(?:mkv|mp4|avi|mov|wmv|flv|webm|m4v)$", re.IGNORECASE)


# ============================================================
# CLEAN URL / LINK / USERNAME
# ============================================================

def _remove_urls_links_usernames(name: str) -> str:
    if not name:
        return ""
    name = _WEB_URL.sub("", name)
    name = _WWW_URL.sub("", name)
    name = _TELEGRAM_LINK.sub("", name)
    name = _URL_LABEL.sub("", name)
    name = _TELEGRAM_USERNAME.sub("", name)
    return name


# ============================================================
# CLEAN SEPARATORS AFTER REMOVAL
# ============================================================

def _clean_removed_parts(name: str) -> str:
    if not name:
        return ""
    name = _RE_SPACES.sub(" ", name)
    name = _RE_SPACE_EXT.sub(".", name)
    name = _RE_TRAILING_SEP_EXT.sub(r"\1", name)
    name = _RE_REPEATED_SPACES.sub(" ", name)
    return name.strip()


# ============================================================
# CLEAN FILE NAME (CACHED ENGINE)
# ============================================================

@lru_cache(maxsize=16384)
def clean_file_name(name: str) -> str:
    if name is None:
        return ""

    name = str(name).replace("\x00", "").strip()
    if not name:
        return ""

    # 1. Strips leading matched prefixes in maximum 5 passes
    for _ in range(5):
        new_name = _RE_COMBINED_PREFIX.sub("", name)
        if new_name == name:
            break
        name = new_name.lstrip()

    # 2. Removes URLs, links, @usernames anywhere in filename
    name = _remove_urls_links_usernames(name)

    # 3. Clean spacing and separator leftovers
    name = _clean_removed_parts(name)
    name = name.lstrip(" \t\r\n-_.:|")
    name = _RE_SPACES.sub(" ", name).strip()

    # 4. Remove video extension for button display
    name = _RE_VIDEO_EXT.sub("", name)

    # 5. Remove brackets like [], (), {}
    name = re.sub(r"[\[\]\(\)\{\}]", " ", name)

    # 6. Replace special characters (_, -, #, dots, symbols) with clean spaces
    name = re.sub(r"[_\-\.+#~*&!|:;\\/]+", " ", name)

    # 7. Strip out any remaining weird punctuation/symbols
    name = re.sub(r"[^\w\s]", " ", name)

    # 8. Single space normalize & strip
    name = _RE_SPACES.sub(" ", name).strip()

    return name or "Movie"


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

def clean_name(name: str):
    cleaned = clean_file_name(name)
    return cleaned or "Unknown"


# ============================================================
# MOVIE NAME CLEANER
# ============================================================

@lru_cache(maxsize=16384)
def clean_movie_name(name: str):
    if not name:
        return "Unknown"

    name = clean_file_name(name)
    name = _RE_VIDEO_EXT.sub("", name)
    name = _RE_SPACES.sub(" ", name).strip()

    return name or "Unknown"


# ============================================================
# EXTENSION NORMALIZER
# ============================================================

@lru_cache(maxsize=256)
def normalize_extension(extension: str):
    if not extension:
        return ""
    ext = str(extension).strip().replace(" ", "")
    if not ext:
        return ""
    return "." + ext.lstrip(".")


# ============================================================
# BACKWARD-COMPATIBLE FILE BUILDER
# ============================================================

def rename_movie_file(movie_name: str, quality: str, extension: str):
    filename = clean_file_name(movie_name)
    if not filename:
        filename = "Movie"

    ext = normalize_extension(extension)
    if ext and not filename.lower().endswith(ext.lower()):
        filename += ext

    return filename
