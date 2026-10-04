import aiohttp
import re
from filters.fsub import is_subscribed


def format_size(size: int):
    if not size:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    size = float(size)

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"


def normalize_text(text: str):
    text = text.lower()
    text = re.sub(r"[_\-.]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_pages(total: int, per_page: int = 7):
    if total == 0:
        return 1
    return (total + per_page - 1) // per_page


def paginate(items: list, page: int, limit: int = 7):
    start = (page - 1) * limit
    end = start + limit
    return items[start:end]


async def get_imdb_suggestions(query: str, limit: int = 10):
    clean_q = normalize_text(query)
    if not clean_q:
        return []

    first_char = clean_q[0]
    url = f"https://v3.sg.media-imdb.com/suggestion/{first_char}/{clean_q}.json"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    titles = []
                    
                    for item in data.get("d", []):
                        # 1. Cast/Celebrities filter:
                        # Titles id 'tt' tho start avthundi (actors/directors di 'nm' tho untundi)
                        item_id = str(item.get("id", ""))
                        if not item_id.startswith("tt"):
                            continue

                        # 2. Type filter: actor, actress, audio lantivi exclude cheyadam
                        entity_type = str(item.get("q", "")).lower()
                        if entity_type in ["actor", "actress", "soundtrack"]:
                            continue

                        title = item.get("l")
                        year = item.get("y")  # IMDb release year

                        if title:
                            # Year unte "Movie Name (2004)" format lo set avthundi
                            display_title = f"{title} ({year})" if year else title

                            if display_title not in titles:
                                titles.append(display_title)

                        if len(titles) >= limit:
                            break

                    return titles
    except Exception as e:
        print(f"IMDb Error: {e}", flush=True)
    return []


async def get_imdb_movie_details(query: str, preferred_lang: str = "te"):
    """
    Fetches high-resolution landscape (16:9) banner image, Title, Year, Rating, Genres, and Runtime.
    Dynamically prioritizes the requested original language (te, en, ta, hi, ml, kn).
    Guaranteed Fallback: If TMDB returns no image, picks from IMDb/OMDB.
    """
    # Extract year if present in query (e.g. 'Kalki 2019' -> 2019)
    extracted_year = None
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", query)
    if year_match:
        extracted_year = year_match.group(1)

    # Brackets lo unna year & extra tags clean chesi search cheyadam
    clean_q = re.sub(r"\(\d{4}\)|\b(19\d\d|20\d\d)\b", "", query).strip()
    clean_q = normalize_text(clean_q)
    if not clean_q:
        return None

    # Mee personal TMDB v3 API Key
    tmdb_key = "7f43669a428c09611a0518fa9c0bbddb"
    
    details = {
        "title": query.title(),
        "year": extracted_year,
        "image": None,
        "rating": "N/A",
        "genres": "N/A",
        "runtime": "N/A"
    }

    # Language priority order: preferred_lang first, then English ('en'), then Telugu ('te')
    target_langs = [preferred_lang]
    if "en" not in target_langs:
        target_langs.append("en")
    if "te" not in target_langs:
        target_langs.append("te")

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Direct Movie Search on TMDB with optional year
            year_query = f"&primary_release_year={extracted_year}" if extracted_year else ""
            tmdb_movie_url = f"https://api.themoviedb.org/3/search/movie?api_key={tmdb_key}&query={clean_q}{year_query}&include_adult=false"
            
            async with session.get(tmdb_movie_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                results = []
                if resp.status == 200:
                    t_data = await resp.json()
                    results = t_data.get("results", [])

                # Fallback without year constraint if direct year search returned empty
                if not results and extracted_year:
                    fallback_url = f"https://api.themoviedb.org/3/search/movie?api_key={tmdb_key}&query={clean_q}&include_adult=false"
                    async with session.get(fallback_url, timeout=aiohttp.ClientTimeout(total=4)) as fb_resp:
                        if fb_resp.status == 200:
                            fb_data = await fb_resp.json()
                            results = fb_data.get("results", [])

                # Fallback to multi-search if direct movie search is still empty
                if not results:
                    tmdb_multi_url = f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&query={clean_q}"
                    async with session.get(tmdb_multi_url, timeout=aiohttp.ClientTimeout(total=4)) as m_resp:
                        if m_resp.status == 200:
                            m_data = await m_resp.json()
                            results = m_data.get("results", [])

                if results:
                    best_item = None

                    # Preference 1: Target language (preferred_lang / en) + landscape backdrop
                    for lang in target_langs:
                        for r in results:
                            if r.get("original_language") == lang and r.get("backdrop_path"):
                                best_item = r
                                break
                        if best_item:
                            break

                    # Preference 2: Target language + poster
                    if not best_item:
                        for lang in target_langs:
                            for r in results:
                                if r.get("original_language") == lang:
                                    best_item = r
                                    break
                            if best_item:
                                break

                    # Preference 3: Any matching item with a backdrop
                    if not best_item:
                        best_item = next((r for r in results if r.get("backdrop_path")), results[0])

                    title = best_item.get("title") or best_item.get("name") or query.title()
                    release_date = best_item.get("release_date") or best_item.get("first_air_date") or ""
                    year = release_date.split("-")[0] if release_date else extracted_year
                    
                    backdrop = best_item.get("backdrop_path")
                    poster = best_item.get("poster_path")

                    # Primary: 16:9 Landscape Backdrop; Fallback: High-res Poster
                    if backdrop:
                        details["image"] = f"https://image.tmdb.org/t/p/w780{backdrop}"
                    elif poster:
                        details["image"] = f"https://image.tmdb.org/t/p/w780{poster}"
                    
                    details["title"] = title
                    details["year"] = year
                    vote = best_item.get("vote_average")
                    if vote:
                        details["rating"] = f"{vote:.1f}"

                    # Runtime and Genres
                    media_type = best_item.get("media_type", "movie")
                    item_id = best_item.get("id")
                    if item_id:
                        info_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={tmdb_key}"
                        try:
                            async with session.get(info_url, timeout=aiohttp.ClientTimeout(total=3)) as info_resp:
                                if info_resp.status == 200:
                                    info_data = await info_resp.json()
                                    genres_list = [g.get("name") for g in info_data.get("genres", []) if g.get("name")]
                                    if genres_list:
                                        details["genres"] = ", ".join(genres_list[:3])
                                    
                                    runtime = info_data.get("runtime") or (info_data.get("episode_run_time") or [0])[0]
                                    if runtime:
                                        hours = runtime // 60
                                        mins = runtime % 60
                                        details["runtime"] = f"{hours}h {mins}m" if hours else f"{mins} min"
                        except Exception:
                            pass
    except Exception as e:
        print(f"TMDB Fetch Error: {e}", flush=True)

    # 2. Fallback to IMDb/OMDB metadata and image if TMDB fails or has no image
    if not details["image"]:
        try:
            first_char = clean_q[0]
            sugg_url = f"https://v3.sg.media-imdb.com/suggestion/{first_char}/{clean_q}.json"

            async with aiohttp.ClientSession() as session:
                async with session.get(sugg_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        movie_item = None
                        for item in data.get("d", []):
                            item_id = str(item.get("id", ""))
                            if item_id.startswith("tt"):
                                movie_item = item
                                break

                        if movie_item:
                            movie_id = movie_item.get("id")
                            if not details.get("title") or details["title"] == query.title():
                                details["title"] = movie_item.get("l") or details["title"]
                            if not details.get("year"):
                                details["year"] = movie_item.get("y") or details["year"]

                            # Direct IMDb image
                            if movie_item.get("i"):
                                details["image"] = movie_item.get("i", {}).get("imageUrl")

                            api_url = f"https://www.omdbapi.com/?i={movie_id}&apikey=trilogy"
                            try:
                                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=3)) as o_resp:
                                    if o_resp.status == 200:
                                        omdb_data = await o_resp.json()
                                        if omdb_data.get("Response") == "True":
                                            if details["rating"] == "N/A":
                                                details["rating"] = omdb_data.get("imdbRating", "N/A")
                                            if details["genres"] == "N/A":
                                                details["genres"] = omdb_data.get("Genre", "N/A")
                                            if details["runtime"] == "N/A":
                                                details["runtime"] = omdb_data.get("Runtime", "N/A")
                                            if not details["image"] and omdb_data.get("Poster") not in [None, "N/A"]:
                                                details["image"] = omdb_data.get("Poster")
                            except Exception:
                                pass
        except Exception as e:
            print(f"IMDb Details Fallback Warning: {e}", flush=True)

    return details
