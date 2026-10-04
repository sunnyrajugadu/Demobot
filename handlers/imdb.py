import html
import json
import re
from urllib.parse import quote_plus

import aiohttp
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import app
from utils.helpers import normalize_text


print("✅ handlers/imdb.py imported (IMDb Full Metadata Fix)", flush=True)


# ============================================================
# IMDb endpoints / HTTP
# ============================================================

IMDB_GRAPHQL_URL = "https://api.graphql.imdb.com/"
IMDB_GRAPHQL_CACHE_URL = "https://caching.graphql.imdb.com/"
IMDB_NAME_URL = "https://www.imdb.com/name/{}/"
IMDB_SUGGESTION_BASE = "https://v3.sg.media-imdb.com/suggestion/"
IMDB_TITLE_URL = "https://www.imdb.com/title/{}"

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=6, sock_read=12)

IMDB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.imdb.com/",
}


# ============================================================
# Generic helpers
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


def deep_find(obj, wanted_keys):
    """Recursively find the first useful value for any key in wanted_keys."""
    wanted = {str(k).lower() for k in wanted_keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in wanted and value not in (None, "", [], {}):
                return value
        for value in obj.values():
            found = deep_find(value, wanted)
            if found not in (None, "", [], {}):
                return found

    elif isinstance(obj, list):
        for value in obj:
            found = deep_find(value, wanted)
            if found not in (None, "", [], {}):
                return found

    return None


def deep_find_all(obj, wanted_keys, output=None):
    if output is None:
        output = []
    wanted = {str(k).lower() for k in wanted_keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in wanted and value not in (None, "", [], {}):
                output.append(value)
            deep_find_all(value, wanted, output)
    elif isinstance(obj, list):
        for value in obj:
            deep_find_all(value, wanted, output)

    return output


def parse_json_ld_scripts(text):
    """Read every JSON-LD block from an IMDb title page."""
    found = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.I | re.S,
    )

    for raw in pattern.findall(text or ""):
        raw = raw.strip()
        if not raw:
            continue
        raw = html.unescape(raw)
        try:
            found.append(json.loads(raw))
        except Exception:
            # Some pages contain malformed/trailing JSON-LD. Ignore only that block.
            continue

    return found


def extract_next_data(text):
    """Extract IMDb's __NEXT_DATA__ object when present."""
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        text or "",
        re.I | re.S,
    )
    if not match:
        return None

    try:
        return json.loads(html.unescape(match.group(1).strip()))
    except Exception:
        return None



def extract_id_from_url(url, prefix):
    if not url:
        return None
    m = re.search(rf"/({re.escape(prefix)}\d+)", str(url), re.I)
    return m.group(1) if m else None


def person_name_from_credit(credit):
    credit = credit if isinstance(credit, dict) else {}
    name_obj = credit.get("name") if isinstance(credit.get("name"), dict) else {}
    name_text = name_obj.get("nameText") if isinstance(name_obj.get("nameText"), dict) else {}
    name = name_text.get("text") or credit.get("text") or name_obj.get("text")
    name_id = name_obj.get("id") or extract_id_from_url(name_obj.get("url"), "nm")
    return clean_text(name, ""), clean_text(name_id, "") if name_id else None


def extract_principal_directors(main):
    directors = []
    for group in main.get("principalCredits") or []:
        group = group if isinstance(group, dict) else {}
        category = group.get("category") if isinstance(group.get("category"), dict) else {}
        cid = str(category.get("id", "")).lower()
        ctext = str(category.get("text", "")).lower()
        if cid != "director" and "director" not in ctext:
            continue
        for credit in group.get("credits") or []:
            name, name_id = person_name_from_credit(credit)
            if name:
                directors.append({"name": name, "id": name_id})

    # Older IMDb page payload fallback.
    if not directors:
        for group in main.get("crewV2") or []:
            group = group if isinstance(group, dict) else {}
            grouping = group.get("grouping") if isinstance(group.get("grouping"), dict) else {}
            gid = str(grouping.get("groupingId", "")).lower()
            gtext = str(grouping.get("text", "")).lower()
            if "director" not in gid and "director" not in gtext:
                continue
            for credit in group.get("credits") or []:
                credit = credit if isinstance(credit, dict) else {}
                name_obj = credit.get("name") if isinstance(credit.get("name"), dict) else {}
                name_text = name_obj.get("nameText") if isinstance(name_obj.get("nameText"), dict) else {}
                name = clean_text(name_text.get("text"), "")
                name_id = name_obj.get("id") or extract_id_from_url(name_obj.get("url"), "nm")
                if name:
                    directors.append({"name": name, "id": name_id})

    final, seen = [], set()
    for person in directors:
        key = person["name"].casefold()
        if key not in seen:
            seen.add(key)
            final.append(person)
    return final


def extract_languages_from_page(main):
    languages = []
    spoken = main.get("spokenLanguages") if isinstance(main.get("spokenLanguages"), dict) else {}
    for item in spoken.get("spokenLanguages") or []:
        item = item if isinstance(item, dict) else {}
        text = item.get("text")
        if not text:
            dp = item.get("displayableProperty") if isinstance(item.get("displayableProperty"), dict) else {}
            value = dp.get("value")
            if isinstance(value, dict):
                text = value.get("plainText") or value.get("text") or value.get("markdown")
            elif value:
                text = value
        if text:
            languages.append(str(text))
    return unique_strings(languages)


def extract_countries_from_page(main):
    countries = []
    details = main.get("countriesDetails") if isinstance(main.get("countriesDetails"), dict) else {}
    for item in details.get("countries") or []:
        item = item if isinstance(item, dict) else {}
        text = item.get("text") or item.get("name")
        if text:
            countries.append(str(text))

    if not countries:
        origin = main.get("countriesOfOrigin") if isinstance(main.get("countriesOfOrigin"), dict) else {}
        for item in origin.get("countries") or []:
            item = item if isinstance(item, dict) else {}
            text = item.get("text") or item.get("name")
            if text:
                countries.append(str(text))
    return unique_strings(countries)


def extract_akas_from_page(main, current_title=None):
    akas = []
    aka_data = main.get("akas") if isinstance(main.get("akas"), dict) else {}
    for edge in aka_data.get("edges") or []:
        node = edge.get("node") if isinstance(edge, dict) and isinstance(edge.get("node"), dict) else {}
        text = node.get("text") or node.get("value")
        if not text:
            tt = node.get("titleText") if isinstance(node.get("titleText"), dict) else {}
            text = tt.get("text")
        if text:
            text = str(text).strip()
            if text and (not current_title or text.casefold() != str(current_title).casefold()):
                akas.append(text)
    return unique_strings(akas)[:8]

def iso_duration_to_text(value):
    if not value:
        return "N/A"

    value = str(value).strip()
    if not value.startswith("P"):
        return value

    hours = re.search(r"(\d+)H", value)
    minutes = re.search(r"(\d+)M", value)
    seconds = re.search(r"(\d+)S", value)

    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0

    if h and m:
        return f"{h} hrs {m} mins"
    if h:
        return f"{h} hrs"
    if m:
        return f"{m} mins"
    if s:
        return f"{s} secs"
    return "N/A"


def format_runtime(runtime_str=None, seconds=None):
    if runtime_str and runtime_str != "N/A":
        runtime_str = str(runtime_str).strip()
        if runtime_str.startswith("PT") or runtime_str.startswith("P"):
            converted = iso_duration_to_text(runtime_str)
            if converted != "N/A":
                return converted
        return runtime_str

    try:
        total_seconds = int(seconds or 0)
        if total_seconds <= 0:
            return "N/A"
        total_minutes = total_seconds // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        if hours and minutes:
            return f"{hours} hrs {minutes} mins"
        if hours:
            return f"{hours} hrs"
        return f"{minutes} mins"
    except Exception:
        return "N/A"


def format_release_date(value, fallback_year=None):
    if isinstance(value, str):
        value = value.strip()
        if value:
            # 2025-01-02 -> January 2, 2025
            match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
            if match:
                y, m, d = match.groups()
                try:
                    months = [
                        "January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"
                    ]
                    return f"{months[int(m) - 1]} {int(d)}, {y}"
                except Exception:
                    pass
            return value

    if isinstance(value, dict):
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        if year:
            try:
                months = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ]
                if month and day:
                    return f"{months[int(month) - 1]} {int(day)}, {year}"
                if month:
                    return f"{months[int(month) - 1]} {year}"
                return str(year)
            except Exception:
                return str(year)

    return clean_text(fallback_year)


def poster_high_res(url):
    # Keep IMDb's original poster URL exactly as provided.
    # Do not force _V1_UY1200_CR0,0,800,1200_AL_.jpg because that
    # can introduce white side edges/cropping compared with IMDb's
    # original poster image.
    return url if url else None


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


def make_hashtags(values):
    tags = []
    for value in values or []:
        value = clean_text(value, "")
        if not value:
            continue
        tag = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
        if tag:
            tags.append(f"#{tag}")
    return " ".join(tags) if tags else "Not Available"


def names_from_json_value(value):
    result = []

    def walk(item):
        if isinstance(item, str):
            # Avoid treating generic labels as people.
            if item.strip():
                result.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                result.append(name.strip())
            else:
                for v in item.values():
                    if isinstance(v, (dict, list)):
                        walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)

    walk(value)
    return unique_strings(result)


def country_names(value):
    result = []

    def walk(item):
        if isinstance(item, str):
            if item.strip():
                result.append(item.strip())
        elif isinstance(item, dict):
            # JSON-LD countryOfOrigin may be {name: "India"}.
            for key in ("name", "text", "country"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    result.append(val.strip())
                    return
            for v in item.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)

    walk(value)
    return unique_strings(result)


def language_names(value):
    result = []

    def walk(item):
        if isinstance(item, str):
            if item.strip():
                result.append(item.strip())
        elif isinstance(item, dict):
            for key in ("name", "text", "language"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    result.append(val.strip())
                    return
            for v in item.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)

    walk(value)
    return unique_strings(result)


# ============================================================
# Google certificate fallback
# ============================================================

GOOGLE_SEARCH_URL = "https://www.google.com/search"
TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_KEY = "7f43669a428c09611a0518fa9c0bbddb"


async def fetch_tmdb_cbfc_certificate(imdb_id, title=None, year=None):
    """Fetch the India/CBFC certificate from TMDB using the IMDb ID.

    TMDB maps the IMDb ID to its own movie ID through /find, then exposes
    country-specific certifications through /movie/{id}/release_dates.
    Only the India (IN) release certification is used here so the rest of
    the IMDb metadata remains untouched.
    """
    if not imdb_id:
        return None

    params = {
        "api_key": TMDB_KEY,
        "external_source": "imdb_id",
    }
    headers = {
        "User-Agent": IMDB_HEADERS["User-Agent"],
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=headers) as session:
            # 1) IMDb ID -> TMDB movie ID
            find_url = f"{TMDB_API_URL}/find/{imdb_id}"
            async with session.get(find_url, params=params) as response:
                if response.status != 200:
                    print(
                        f"TMDB Find Certificate HTTP {response.status} [{imdb_id}]",
                        flush=True,
                    )
                    return None
                find_data = await response.json(content_type=None)

            movie_results = find_data.get("movie_results") or []
            if not movie_results:
                return None

            # Prefer a result whose title/year agrees with IMDb when there are
            # multiple matches; otherwise use the first TMDB movie result.
            selected = None
            target_title = str(title or "").strip().casefold()
            target_year = str(year or "").strip()

            for item in movie_results:
                item_title = str(item.get("title") or item.get("original_title") or "").strip()
                release_date = str(item.get("release_date") or "")
                item_year = release_date[:4] if release_date else ""

                title_match = target_title and (
                    item_title.casefold() == target_title
                    or str(item.get("original_title") or "").strip().casefold() == target_title
                )
                year_match = target_year and item_year == target_year

                if title_match and (not target_year or year_match):
                    selected = item
                    break

            if selected is None:
                selected = movie_results[0]

            tmdb_movie_id = selected.get("id")
            if not tmdb_movie_id:
                return None

            # 2) TMDB movie -> regional release dates/certifications
            release_url = f"{TMDB_API_URL}/movie/{tmdb_movie_id}/release_dates"
            async with session.get(
                release_url,
                params={"api_key": TMDB_KEY},
            ) as response:
                if response.status != 200:
                    print(
                        f"TMDB Release Dates HTTP {response.status} [{imdb_id}/{tmdb_movie_id}]",
                        flush=True,
                    )
                    return None
                release_data = await response.json(content_type=None)

        countries = release_data.get("results") or []
        india = next(
            (
                item for item in countries
                if str(item.get("iso_3166_1") or "").upper() == "IN"
            ),
            None,
        )
        if not india:
            return None

        release_entries = india.get("release_dates") or []
        if not release_entries:
            return None

        # TMDB release-date types:
        # 1 = Premiere, 2 = Theatrical (limited), 3 = Theatrical,
        # 4 = Digital, 5 = Physical, 6 = TV.
        # For a CBFC certificate, theatrical entries are the useful ones.
        type_priority = {3: 0, 2: 1, 1: 2, 4: 3, 5: 4, 6: 5}
        candidates = []

        for entry in release_entries:
            certification = clean_text(entry.get("certification"), "")
            if not certification:
                continue

            raw_type = entry.get("type")
            try:
                release_type = int(raw_type)
            except (TypeError, ValueError):
                release_type = 99

            release_date = str(entry.get("release_date") or "")
            candidates.append((
                type_priority.get(release_type, 99),
                release_date,
                certification,
            ))

        if not candidates:
            return None

        # Prefer theatrical certification, then the most recent entry within
        # that type. This also handles TMDB entries that contain multiple
        # Indian release records for the same movie.
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=False)
        best_priority = candidates[0][0]
        same_priority = [item for item in candidates if item[0] == best_priority]
        same_priority.sort(key=lambda item: item[1], reverse=True)
        certificate = same_priority[0][2].strip()

        return normalize_certificate(certificate) or None

    except Exception as exc:
        print(f"TMDB CBFC Certificate Error [{imdb_id}]: {exc}", flush=True)
        return None


# ============================================================
# IMDb page metadata
# ============================================================

async def fetch_imdb_title_page(imdb_id):
    url = IMDB_TITLE_URL.format(imdb_id) + "/"
    headers = dict(IMDB_HEADERS)

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                raise RuntimeError(f"IMDb title page HTTP {response.status}")
            return await response.text(errors="ignore")


def extract_title_from_jsonld(blocks):
    for block in blocks:
        candidates = block if isinstance(block, list) else [block]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") in ("Movie", "TVSeries", "TVEpisode", "TVMovie", "CreativeWork"):
                title = item.get("name")
                if title:
                    return title
    return None


def extract_jsonld_details(blocks):
    """Extract the stable schema.org fields IMDb publishes on title pages."""
    out = {}

    for block in blocks:
        items = block if isinstance(block, list) else [block]
        for item in items:
            if not isinstance(item, dict):
                continue

            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if not any(t in {"Movie", "TVSeries", "TVEpisode", "TVMovie", "CreativeWork"} for t in types if t):
                continue

            out.setdefault("title", item.get("name"))
            out.setdefault("image", item.get("image"))
            out.setdefault("datePublished", item.get("datePublished"))
            out.setdefault("duration", item.get("duration"))
            out.setdefault("genre", item.get("genre"))
            out.setdefault("inLanguage", item.get("inLanguage"))
            out.setdefault("countryOfOrigin", item.get("countryOfOrigin"))
            out.setdefault("description", item.get("description"))
            out.setdefault("director", item.get("director"))
            out.setdefault("creator", item.get("creator"))
            out.setdefault("aggregateRating", item.get("aggregateRating"))
            out.setdefault("contentRating", item.get("contentRating"))
            out.setdefault("alternateName", item.get("alternateName"))

    return out


def extract_jsonld_people(value):
    people = []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("text")
            url = item.get("url")
            if name:
                people.append({
                    "name": str(name).strip(),
                    "id": extract_id_from_url(url, "nm") if url else None,
                })
        elif isinstance(item, str) and item.strip():
            people.append({"name": item.strip(), "id": None})
    final, seen = [], set()
    for person in people:
        key = person["name"].casefold()
        if key not in seen:
            seen.add(key)
            final.append(person)
    return final


def first_text(value):
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("text", "name", "plainText", "value", "rating"):
            val = value.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for val in value.values():
            found = first_text(val)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = first_text(item)
            if found:
                return found
    return None


# ============================================================
# Small GraphQL calls only for reliable IMDb fields
# ============================================================

async def imdb_graphql(query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": IMDB_HEADERS["User-Agent"],
        "Origin": "https://www.imdb.com",
        "Referer": "https://www.imdb.com/",
    }

    last_error = None
    for endpoint in (IMDB_GRAPHQL_CACHE_URL, IMDB_GRAPHQL_URL):
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=headers) as session:
                async with session.post(endpoint, json=payload) as response:
                    text = await response.text(errors="ignore")
                    if response.status != 200:
                        last_error = RuntimeError(
                            f"IMDb GraphQL HTTP {response.status}: {text[:250]}"
                        )
                        continue
                    try:
                        return json.loads(text)
                    except Exception as exc:
                        last_error = exc
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"IMDb GraphQL failed: {last_error}")


IMDB_EXTENDED_QUERY = r'''
query GetTitleExtended($id: ID!) {
  title(id: $id) {
    id
    certificate {
      rating
      country { text }
    }
    certificates(first: 10) {
      edges {
        node {
          rating
          country { text }
        }
      }
    }
    principalCredits {
      category { id text }
      credits {
        name {
          id
          nameText { text }
        }
      }
    }
    credits(first: 10, filter: { categories: ["director"] }) {
      edges {
        node {
          name {
            id
            nameText { text }
          }
          category { id text }
        }
      }
    }
    spokenLanguages {
      spokenLanguages(limit: 10) {
        id
        text
      }
    }
    countriesOfOrigin {
      countries {
        id
        text
      }
    }
    akas(first: 10) {
      edges {
        node {
          text
          country { text }
          language { text }
        }
      }
    }
  }
}
'''


async def fetch_imdb_extended_graphql(imdb_id):
    try:
        payload = await imdb_graphql(IMDB_EXTENDED_QUERY, {"id": imdb_id})
        title = ((payload.get("data") or {}).get("title"))
        if not isinstance(title, dict):
            return {}
        return title
    except Exception as exc:
        print(f"IMDb Extended GraphQL Error [{imdb_id}]: {exc}", flush=True)
        return {}


IMDB_CORE_QUERY = r'''
query GetTitleCore($id: ID!) {
  title(id: $id) {
    id
    titleText { text }
    originalTitleText { text }
    releaseYear { year endYear }
    releaseDate { day month year }
    runtime { seconds }
    ratingsSummary { aggregateRating voteCount }
    titleGenres { genres { genre { text } } }
    primaryImage { url }
    plot { plotText { plainText } }
  }
}
'''


async def fetch_imdb_core_graphql(imdb_id):
    payload = await imdb_graphql(IMDB_CORE_QUERY, {"id": imdb_id})
    title = ((payload.get("data") or {}).get("title"))
    if not title:
        return {}
    return title


# ============================================================
# Search
# ============================================================

IMDB_SEARCH_QUERY = r'''
query SearchTitles($searchTerm: String!, $first: Int!) {
  mainSearch(first: $first, options: { searchTerm: $searchTerm, type: TITLE }) {
    edges {
      node {
        entity {
          ... on Title {
            id
            titleText { text }
            releaseYear { year }
            ratingsSummary { aggregateRating }
            primaryImage { url }
            titleGenres { genres { genre { text } } }
          }
        }
      }
    }
  }
}
'''


async def fetch_imdb_results_graphql(query, limit=10):
    payload = await imdb_graphql(
        IMDB_SEARCH_QUERY,
        {"searchTerm": query, "first": max(1, min(int(limit), 25))},
    )

    results = []
    edges = (((payload.get("data") or {}).get("mainSearch") or {}).get("edges") or [])

    for edge in edges:
        entity = ((edge.get("node") or {}).get("entity") or {})
        item_id = str(entity.get("id", ""))
        if not item_id.startswith("tt"):
            continue

        title = ((entity.get("titleText") or {}).get("text"))
        if not title:
            continue

        genres = []
        for item in ((entity.get("titleGenres") or {}).get("genres") or []):
            genre = ((item.get("genre") or {}).get("text"))
            if genre:
                genres.append(genre)

        results.append({
            "id": item_id,
            "title": title,
            "year": str((entity.get("releaseYear") or {}).get("year") or "N/A"),
            "poster": (entity.get("primaryImage") or {}).get("url"),
            "rating": str((entity.get("ratingsSummary") or {}).get("aggregateRating") or "N/A"),
            "genres": unique_strings(genres),
        })

        if len(results) >= limit:
            break

    return results


async def fetch_imdb_results_suggestion(query, limit=10):
    clean_q = normalize_text(query)
    if not clean_q:
        return []

    first_char = quote_plus(clean_q[0])
    encoded_query = quote_plus(clean_q)
    url = f"{IMDB_SUGGESTION_BASE}{first_char}/{encoded_query}.json"

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url, headers=IMDB_HEADERS) as response:
                if response.status != 200:
                    return []
                data = await response.json(content_type=None)

        results = []
        for item in data.get("d", []):
            item_id = str(item.get("id", ""))
            if not item_id.startswith("tt"):
                continue

            entity_type = str(item.get("q", "")).lower()
            if entity_type in {"actor", "actress", "soundtrack"}:
                continue

            title = item.get("l")
            if not title:
                continue

            results.append({
                "id": item_id,
                "title": title,
                "year": str(item.get("y")) if item.get("y") else "N/A",
                "poster": (item.get("i") or {}).get("imageUrl"),
                "rating": str(item.get("r")) if item.get("r") is not None else "N/A",
                "genres": unique_strings(item.get("gen") or []),
            })

            if len(results) >= limit:
                break

        return results
    except Exception as exc:
        print(f"IMDb Suggestion Search Error: {exc}", flush=True)
        return []


async def fetch_imdb_results(query, limit=10):
    clean_q = normalize_text(query)
    if not clean_q:
        return []

    try:
        results = await fetch_imdb_results_graphql(clean_q, limit)
        if results:
            return results
    except Exception as exc:
        print(f"IMDb GraphQL Search Error: {exc}", flush=True)

    return await fetch_imdb_results_suggestion(clean_q, limit)


# ============================================================
# FULL IMDb DETAILS
# ============================================================

async def fetch_full_movie_details(
    imdb_id: str,
    fallback_title=None,
    fallback_year=None,
    fallback_poster=None,
    fallback_rating=None,
    fallback_genres=None,
    fallback_director=None,
):
    data = {
        "id": imdb_id,
        "title": fallback_title or "N/A",
        "original_title": None,
        "year": fallback_year or "N/A",
        "rating": fallback_rating or "N/A",
        "vote_count": None,
        "release_date": fallback_year or "N/A",
        "runtime": "N/A",
        "director": [],
        "genres": unique_strings(fallback_genres or []),
        "languages": [],
        "countries": [],
        "storyline": "No storyline available.",
        "poster": fallback_poster,
        "aka": [],
        "certificate": None,
        "imdb_url": IMDB_TITLE_URL.format(imdb_id),
        "trailer_url": None,
    }

    # IMDb's __NEXT_DATA__ is the key source for the fields that were N/A.
    # In particular:
    # mainColumnData.principalCredits -> directors
    # mainColumnData.spokenLanguages -> languages
    # mainColumnData.countriesDetails -> countries
    # mainColumnData.akas -> alternate titles
    try:
        page = await fetch_imdb_title_page(imdb_id)
        jsonld_blocks = parse_json_ld_scripts(page)
        jsonld = extract_jsonld_details(jsonld_blocks)

        if jsonld.get("title"):
            data["title"] = clean_text(jsonld["title"], data["title"])
        if jsonld.get("image"):
            image = jsonld["image"]
            if isinstance(image, list):
                image = image[0] if image else None
            if image:
                data["poster"] = poster_high_res(image)
        if jsonld.get("datePublished"):
            data["release_date"] = format_release_date(jsonld["datePublished"], data["year"])
            m = re.match(r"^(\d{4})", str(jsonld["datePublished"]))
            if m:
                data["year"] = m.group(1)
        if jsonld.get("duration"):
            data["runtime"] = format_runtime(jsonld["duration"])
        if jsonld.get("genre"):
            genres = jsonld["genre"] if isinstance(jsonld["genre"], list) else [jsonld["genre"]]
            parsed = unique_strings(genres)
            if parsed:
                data["genres"] = parsed
        if jsonld.get("description"):
            data["storyline"] = clean_text(jsonld["description"], data["storyline"])
        if jsonld.get("contentRating"):
            certificate = jsonld["contentRating"]
            if isinstance(certificate, list):
                certificate = certificate[0] if certificate else None
            if isinstance(certificate, dict):
                certificate = certificate.get("rating") or certificate.get("name") or certificate.get("text")
            if certificate:
                data["certificate"] = clean_text(certificate, "") or None

        # JSON-LD fallback for credits, languages, countries and alternate names.
        if not data["director"] and jsonld.get("director"):
            data["director"] = extract_jsonld_people(jsonld.get("director"))
        if not data["languages"] and jsonld.get("inLanguage"):
            data["languages"] = language_names(jsonld.get("inLanguage"))
        if not data["countries"] and jsonld.get("countryOfOrigin"):
            data["countries"] = country_names(jsonld.get("countryOfOrigin"))
        if not data["aka"] and jsonld.get("alternateName"):
            alt = jsonld.get("alternateName")
            data["aka"] = unique_strings(alt if isinstance(alt, list) else [alt])[:8]

        aggregate = jsonld.get("aggregateRating") or {}
        if isinstance(aggregate, dict):
            if aggregate.get("ratingValue") is not None:
                data["rating"] = str(aggregate["ratingValue"])
            if aggregate.get("ratingCount") is not None:
                try:
                    data["vote_count"] = int(aggregate["ratingCount"])
                except Exception:
                    data["vote_count"] = aggregate["ratingCount"]

        next_data = extract_next_data(page)
        if next_data:
            page_props = (next_data.get("props") or {}).get("pageProps") or {}
            above = page_props.get("aboveTheFoldData") or {}
            main = page_props.get("mainColumnData") or {}
            if not isinstance(main, dict):
                main = {}

            # IMDb occasionally moves these objects in its page payload.
            # Keep the exact current paths first, then use recursive fallbacks.
            principal_payload = main.get("principalCredits")
            if not principal_payload:
                principal_payload = deep_find(next_data, ["principalCredits"]) or []
            spoken_payload = main.get("spokenLanguages")
            if not spoken_payload:
                spoken_payload = deep_find(next_data, ["spokenLanguages"]) or {}
            countries_payload = main.get("countriesDetails") or main.get("countriesOfOrigin")
            if not countries_payload:
                countries_payload = deep_find(next_data, ["countriesDetails"]) or deep_find(next_data, ["countriesOfOrigin"]) or {}
            aka_payload = main.get("akas")
            if not aka_payload:
                aka_payload = deep_find(next_data, ["akas"]) or {}

            title_text = (above.get("titleText") or {}).get("text")
            if title_text:
                data["title"] = title_text

            original_title = (above.get("originalTitleText") or {}).get("text")
            if original_title and original_title.casefold() != str(data["title"]).casefold():
                data["original_title"] = original_title

            release_year = main.get("releaseYear") or above.get("releaseYear") or {}
            if release_year.get("year"):
                data["year"] = str(release_year["year"])

            release_date = main.get("releaseDate") or {}
            if release_date:
                data["release_date"] = format_release_date(release_date, data["year"])

            rating_summary = above.get("ratingsSummary") or main.get("ratingsSummary") or {}
            if rating_summary.get("aggregateRating") is not None:
                data["rating"] = str(rating_summary["aggregateRating"])
            if rating_summary.get("voteCount") is not None:
                data["vote_count"] = rating_summary["voteCount"]

            runtime = main.get("runtime") or above.get("runtime") or {}
            if runtime:
                displayable = runtime.get("displayableProperty") or {}
                value = displayable.get("value") or {}
                runtime_text = value.get("plainText") or value.get("text") or value.get("markdown")
                if runtime_text:
                    data["runtime"] = format_runtime(runtime_text)
                elif runtime.get("seconds"):
                    data["runtime"] = format_runtime(seconds=runtime["seconds"])

            genres_container = main.get("genres") or above.get("genres") or {}
            parsed_genres = []
            for item in genres_container.get("genres") or []:
                item = item if isinstance(item, dict) else {}
                genre_text = item.get("text") or (item.get("genre") or {}).get("text")
                if genre_text:
                    parsed_genres.append(genre_text)
            if parsed_genres:
                data["genres"] = unique_strings(parsed_genres)

            poster = (above.get("primaryImage") or {}).get("url") or (main.get("primaryImage") or {}).get("url")
            if poster:
                data["poster"] = poster_high_res(poster)

            plot = main.get("plot") or above.get("plot") or {}
            plot_text = (plot.get("plotText") or {}).get("plainText")
            if not plot_text:
                edges = (main.get("summaries") or {}).get("edges") or []
                if edges:
                    plot_text = (((edges[0].get("node") or {}).get("plotText") or {}).get("plainText"))
            if plot_text:
                data["storyline"] = plot_text.strip()

            certificate_obj = main.get("certificate") or above.get("certificate") or {}
            if isinstance(certificate_obj, dict):
                certificate = certificate_obj.get("rating") or certificate_obj.get("text") or certificate_obj.get("name")
            else:
                certificate = certificate_obj
            if certificate:
                data["certificate"] = str(certificate).strip()

            director_source = dict(main)
            director_source["principalCredits"] = principal_payload
            directors = extract_principal_directors(director_source)
            if directors:
                data["director"] = directors

            language_source = dict(main)
            language_source["spokenLanguages"] = spoken_payload if isinstance(spoken_payload, dict) else {}
            languages = extract_languages_from_page(language_source)
            if languages:
                data["languages"] = languages

            country_source = dict(main)
            if isinstance(countries_payload, dict):
                if countries_payload.get("countriesDetails"):
                    country_source["countriesDetails"] = countries_payload.get("countriesDetails")
                elif countries_payload.get("countriesOfOrigin"):
                    country_source["countriesOfOrigin"] = countries_payload.get("countriesOfOrigin")
                elif countries_payload.get("countries"):
                    country_source["countriesDetails"] = countries_payload
            countries = extract_countries_from_page(country_source)
            if countries:
                data["countries"] = countries

            aka_source = dict(main)
            aka_source["akas"] = aka_payload if isinstance(aka_payload, dict) else {}
            akas = extract_akas_from_page(aka_source, data["title"])
            if akas:
                data["aka"] = akas

    except Exception as exc:
        print(f"IMDb Title Page Error [{imdb_id}]: {exc}", flush=True)

    # Small GraphQL fallback for core fields. It is deliberately kept separate
    # so an unsupported optional field cannot wipe out all metadata.
    try:
        core = await fetch_imdb_core_graphql(imdb_id)
        if core:
            title_text = (core.get("titleText") or {}).get("text")
            original_title = (core.get("originalTitleText") or {}).get("text")
            release_year = core.get("releaseYear") or {}
            release_date = core.get("releaseDate") or {}
            runtime = core.get("runtime") or {}
            ratings = core.get("ratingsSummary") or {}

            if title_text:
                data["title"] = title_text
            if original_title and original_title.casefold() != str(data["title"]).casefold():
                data["original_title"] = original_title
            if release_year.get("year"):
                data["year"] = str(release_year["year"])
            if release_date:
                data["release_date"] = format_release_date(release_date, data["year"])
            if ratings.get("aggregateRating") is not None:
                data["rating"] = str(ratings["aggregateRating"])
            if ratings.get("voteCount") is not None:
                data["vote_count"] = ratings["voteCount"]
            if runtime.get("seconds"):
                data["runtime"] = format_runtime(seconds=runtime["seconds"])

            genres = []
            for item in (core.get("titleGenres") or {}).get("genres") or []:
                genre = (item.get("genre") or {}).get("text")
                if genre:
                    genres.append(genre)
            if genres:
                data["genres"] = unique_strings(genres)

            image = (core.get("primaryImage") or {}).get("url")
            if image:
                data["poster"] = poster_high_res(image)

            plot = (core.get("plot") or {}).get("plotText") or {}
            if plot.get("plainText"):
                data["storyline"] = plot["plainText"].strip()
    except Exception as exc:
        print(f"IMDb Core GraphQL Error [{imdb_id}]: {exc}", flush=True)

    data["rating"] = clean_text(data["rating"], "N/A")
    data["release_date"] = clean_text(data["release_date"], data["year"] or "N/A")
    data["director"] = data["director"] or []
    data["languages"] = data["languages"] or []
    data["countries"] = data["countries"] or []
    data["aka"] = data["aka"] or []
    data["poster"] = data["poster"] or None

    # Final metadata fallback. These fields are queried independently from IMDb
    # so a missing optional field can never erase the fields already collected.
    extended = await fetch_imdb_extended_graphql(imdb_id)
    if extended:
        certificate_text = first_text(extended.get("certificate"))
        if certificate_text:
            data["certificate"] = certificate_text

        if not data["director"]:
            directors = []
            for group in extended.get("principalCredits") or []:
                category = group.get("category") or {}
                if str(category.get("id", "")).lower() != "director" and "director" not in str(category.get("text", "")).lower():
                    continue
                for credit in group.get("credits") or []:
                    name_obj = credit.get("name") or {}
                    name_text = name_obj.get("nameText") or {}
                    name = name_text.get("text")
                    if name:
                        directors.append({"name": name, "id": name_obj.get("id")})
            for edge in ((extended.get("credits") or {}).get("edges") or []):
                node = edge.get("node") or {}
                name_obj = node.get("name") or {}
                name_text = name_obj.get("nameText") or {}
                name = name_text.get("text")
                if name:
                    directors.append({"name": name, "id": name_obj.get("id")})
            unique_directors = []
            seen_directors = set()
            for person in directors:
                key = person["name"].casefold()
                if key not in seen_directors:
                    seen_directors.add(key)
                    unique_directors.append(person)
            if unique_directors:
                data["director"] = unique_directors

        if not data["languages"]:
            data["languages"] = unique_strings([
                item.get("text") for item in
                ((extended.get("spokenLanguages") or {}).get("spokenLanguages") or [])
                if isinstance(item, dict) and item.get("text")
            ])

        if not data["countries"]:
            data["countries"] = unique_strings([
                item.get("text") for item in
                ((extended.get("countriesOfOrigin") or {}).get("countries") or [])
                if isinstance(item, dict) and item.get("text")
            ])

        if not data["aka"]:
            aka_values = []
            for edge in ((extended.get("akas") or {}).get("edges") or []):
                node = edge.get("node") or {}
                text = node.get("text")
                if text and text.casefold() != str(data["title"]).casefold():
                    aka_values.append(text)
            data["aka"] = unique_strings(aka_values)[:8]

    # IMDb sometimes leaves certificate empty/generic. Fetch ONLY the India
    # CBFC certificate from TMDB; every other field remains exactly as collected
    # above from IMDb. If TMDB cannot provide it, keep the IMDb value.
    try:
        tmdb_certificate = await fetch_tmdb_cbfc_certificate(
            imdb_id,
            data["title"],
            data.get("year"),
        )
        if tmdb_certificate:
            data["certificate"] = tmdb_certificate
    except Exception as exc:
        print(f"TMDB CBFC Certificate Fallback Error [{imdb_id}]: {exc}", flush=True)

    # Do not print the literal N/A for these fields. IMDb can genuinely omit
    # metadata for some titles, so use a neutral label only as a last resort.
    data["director"] = data["director"] or [{"name": "Not Available", "id": None}]
    data["languages"] = data["languages"] or ["Not Available"]
    data["countries"] = data["countries"] or ["Not Available"]

    trailer_query = quote_plus(f"{data['title']} {data['year']} official trailer")
    data["trailer_url"] = f"https://www.youtube.com/results?search_query={trailer_query}"
    return data


# ============================================================
# /imdb command
# ============================================================

@app.on_message(filters.private & filters.command(["imdb"]))
async def imdb_search_command(client, message: Message):
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                "💡 <b>Usage Guide :</b>\n"
                "» <code>/imdb &lt;movie_name&gt;</code>\n"
                "» <i>Example :</i> <code>/imdb Salaar</code>",
                quote=True,
            )

        query = parts[1].strip()
        search_msg = await message.reply_text(
            "⚡ <b>Searching IMDb database...</b>",
            quote=True,
        )

        results = await fetch_imdb_results(query, limit=10)
        if not results:
            return await search_msg.edit_text(
                f"🥀 <b>No matching results found for :</b> "
                f"<code>{html.escape(query)}</code>"
            )

        buttons = []
        for item in results:
            btn_text = f"{item['title']} - {item['year']}"
            # IMPORTANT: only IMDb ID. No 64-byte truncation.
            buttons.append([
                InlineKeyboardButton(
                    text=btn_text[:64],
                    callback_data=f"imdb_view:{item['id']}",
                )
            ])

        buttons.append([
            InlineKeyboardButton("Close", callback_data="close")
        ])

        header_text = (
            f"🎯 <b>Matched Results For :</b> "
            f"<code>{html.escape(query.title())}</code>\n"
            f"<i>👇 Choose the exact title below to view full IMDb details :</i>"
        )

        await search_msg.edit_text(
            text=header_text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    except Exception as exc:
        print(f"IMDb Command Error: {exc}", flush=True)
        try:
            await message.reply_text(
                "⚠️ Something went wrong while searching IMDb.",
                quote=True,
            )
        except Exception:
            pass


# ============================================================
# IMDb detail callback
# ============================================================

@app.on_callback_query(filters.regex(r"^imdb_view:(tt\d+)$"))
async def imdb_view_callback(client, query: CallbackQuery):
    try:
        imdb_id = query.matches[0].group(1)
        await query.answer("Fetching exact IMDb details...")

        orig_message = query.message.reply_to_message or query.message

        try:
            await query.message.delete()
        except Exception:
            pass

        info = await fetch_full_movie_details(imdb_id)

        me = await client.get_me()
        bot_user = me.username or "CinemaVetaBot"
        bot_mention = (
            f'<a href="https://t.me/{html.escape(bot_user)}">'
            f'<b>@{html.escape(bot_user)}</b></a>'
        )

        genre_str = make_hashtags(info["genres"])
        lang_str = make_hashtags(info["languages"])
        country_str = make_hashtags(info["countries"])

        if info["rating"] != "N/A":
            rating_disp = f"{html.escape(str(info['rating']))} / 10"
        else:
            rating_disp = "Not Available / 10"

        vote_count = info.get("vote_count")
        try:
            vote_count = int(vote_count) if vote_count is not None else None
        except (TypeError, ValueError):
            vote_count = None
        vote_disp = f" ({vote_count:,} votes)" if vote_count is not None else ""

        certificate = normalize_certificate(info.get("certificate"))
        certificate_disp = f" [{html.escape(certificate)}]" if certificate else ""

        title_link = (
            f'<a href="{info["imdb_url"]}">'
            f'<b>{html.escape(info["title"])} '
            f'[{html.escape(str(info["year"]))}]</b></a>'
        )

        caption_lines = [f"🎬 {title_link}\n"]

        if info.get("original_title"):
            original_link = (
                f'<a href="{html.escape(info["imdb_url"])}">'
                f'{html.escape(str(info["original_title"]))}</a>'
            )
            caption_lines.append(
                f"📝 <b>Original Title :</b> {original_link}"
            )

        if info.get("aka"):
            aka_links = [
                f'<a href="{html.escape(info["imdb_url"])}">'
                f'{html.escape(str(aka))}</a>'
                for aka in info["aka"]
            ]
            caption_lines.append(
                f"🏷 <b>Also Known As :</b> {', '.join(aka_links)}"
            )

        caption_lines.extend([
            f"⭐ <b>IMDb Rating :</b> {rating_disp}{vote_disp}",
            f"🔞 <b>Certificate :</b> "
            f"{html.escape(str(info['certificate']))}",
            f"🗓 <b>Release Info :</b> "
            f"{html.escape(str(info['release_date']) if info['release_date'] != 'N/A' else 'Not Available')}",
            f"⏳ <b>Runtime :</b> {html.escape(str(info['runtime']) if info['runtime'] != 'N/A' else 'Not Available')}",
        ])
        

        directors = info.get("director") or []
        director_links = []
        for director in directors:
            if isinstance(director, dict):
                name = director.get("name")
                name_id = director.get("id")
            else:
                name = str(director)
                name_id = None
            if not name:
                continue
            if name_id:
                director_links.append(
                    f'<a href="{html.escape(IMDB_NAME_URL.format(name_id))}">'
                    f'{html.escape(name)}</a>'
                )
            else:
                director_links.append(html.escape(name))
        director_text = ", ".join(director_links) if director_links else "N/A"

        caption_lines.extend([
            f"🎥 <b>Directed By :</b> {director_text}",
            f"🎭 <b>Genre :</b> {genre_str}",
            f"🌐 <b>Language :</b> {lang_str}",
            f"🌍 <b>Country Of Origin :</b> {country_str}",
        ])


        caption_lines.extend([
            "",
            "📖 <b>Storyline :</b>",
            html.escape(str(info["storyline"])),
            "",
            f"✨ <b>Powered By :</b>\n{bot_mention}",
        ])

        final_caption = "\n".join(caption_lines)

        buttons = [
            [
                InlineKeyboardButton(
                    f"🔗 View {info['title'][:40]} on IMDb",
                    url=info["imdb_url"],
                )
            ],
            [
                InlineKeyboardButton(
                    "🎥 Watch Trailer",
                    url=info["trailer_url"],
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        sent = False

        if info.get("poster"):
            try:
                await client.send_photo(
                    chat_id=orig_message.chat.id,
                    photo=info["poster"],
                    caption=final_caption,
                    reply_markup=reply_markup,
                    reply_to_message_id=orig_message.id,
                )
                sent = True
            except Exception as photo_error:
                print(f"IMDb Photo Send Error: {photo_error}", flush=True)

        if not sent:
            await client.send_message(
                chat_id=orig_message.chat.id,
                text=final_caption,
                reply_markup=reply_markup,
                reply_to_message_id=orig_message.id,
                disable_web_page_preview=False,
            )

    except Exception as exc:
        print(f"IMDb View Callback Error: {exc}", flush=True)
        try:
            await query.answer(
                "❌ Failed to fetch IMDb details.",
                show_alert=True,
            )
        except Exception:
            pass
