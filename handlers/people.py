import html
import aiohttp
from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from bot import app
from utils.helpers import normalize_text


print("✅ handlers/people.py imported (/people command flow)", flush=True)

TMDB_KEY = "7f43669a428c09611a0518fa9c0bbddb"


# ================= FETCH PERSON FILMOGRAPHY ================= #

async def fetch_person_results(query: str):
    clean_q = normalize_text(query)
    if not clean_q:
        return None, []

    first_char = clean_q[0]
    url = f"https://v3.sg.media-imdb.com/suggestion/{first_char}/{clean_q}.json"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    person_id = None
                    person_name = query.title()

                    # Find matching person ID starting with 'nm'
                    for item in data.get("d", []):
                        item_id = str(item.get("id", ""))
                        if item_id.startswith("nm"):
                            person_id = item_id
                            person_name = item.get("l", query.title())
                            break

                    if not person_id:
                        return None, []

                    movies = []
                    tmdb_url = f"https://api.themoviedb.org/3/find/{person_id}?api_key={TMDB_KEY}&external_source=imdb_id"
                    async with session.get(tmdb_url, timeout=aiohttp.ClientTimeout(total=4)) as t_resp:
                        if t_resp.status == 200:
                            t_data = await t_resp.json()
                            person_tmdb_id = None
                            
                            if t_data.get("person_results"):
                                person_tmdb_id = t_data["person_results"][0].get("id")

                            if person_tmdb_id:
                                credits_url = f"https://api.themoviedb.org/3/person/{person_tmdb_id}/combined_credits?api_key={TMDB_KEY}"
                                async with session.get(credits_url, timeout=aiohttp.ClientTimeout(total=4)) as c_resp:
                                    if c_resp.status == 200:
                                        c_data = await c_resp.json()
                                        all_credits = c_data.get("cast", []) + c_data.get("crew", [])
                                        
                                        seen_ids = set()
                                        for m in all_credits:
                                            m_id = m.get("id")
                                            if m_id in seen_ids:
                                                continue
                                            seen_ids.add(m_id)

                                            title = m.get("title") or m.get("name")
                                            date = m.get("release_date") or m.get("first_air_date") or ""
                                            year = date.split("-")[0] if date else "N/A"

                                            if title:
                                                movies.append({
                                                    "title": title,
                                                    "year": year
                                                })

                    return person_name, movies[:15]
    except Exception as e:
        print(f"Person Search Error: {e}", flush=True)
    return None, []


# ================= /people COMMAND HANDLER ================= #

@app.on_message(filters.private & filters.command(["people","pe"]))
async def person_search_command(client, message: Message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                "💡 <b>Usage Guide :</b>\n"
                "» <code>/people &lt;name&gt;</code>\n"
                "» <i>Example :</i> <code>/people Prabhas</code>",
                quote=True
            )

        query = parts[1].strip()
        search_msg = await message.reply_text("⚡ <b>Searching filmography...</b>", quote=True)

        person_name, movies = await fetch_person_results(query)
        if not movies:
            return await search_msg.edit_text(f"🥀 <b>No filmography found for :</b> <code>{html.escape(query)}</code>")

        # Clean text buttons matching 3rd picture style (Title - Year)
        buttons = []
        for item in movies:
            btn_text = f"{item['title']} - {item['year']}"
            buttons.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"imdb_view_query:{item['title']} ({item['year']})"
                )
            ])

        buttons.append([
            InlineKeyboardButton("Close", callback_data="close")
        ])

        header_text = (
            f"🎯 <b>Filmography For :</b> <code>{html.escape(person_name)}</code>\n"
            f"<i>👇 Choose any movie below to view full details :</i>"
        )

        await search_msg.edit_text(
            text=header_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        print(f"People Command Error: {e}", flush=True)
        try:
            await message.reply_text("⚠️ Something went wrong while searching.", quote=True)
        except Exception:
            pass


# ================= HELPER CALLBACK FOR MOVIE SELECTION ================= #

@app.on_callback_query(filters.regex(r"^imdb_view_query:(.*)"))
async def person_movie_view_callback(client, query: CallbackQuery):
    try:
        movie_query = query.data.split(":", 1)[1].strip()
        await query.answer(f"Fetching details for {movie_query}...")

        try:
            await query.message.delete()
        except Exception:
            pass

        from handlers.imdb import fetch_imdb_results, imdb_view_callback
        results = await fetch_imdb_results(movie_query, limit=1)
        
        if results:
            query.data = f"imdb_view:{results[0]['id']}"
            await imdb_view_callback(client, query)
        else:
            await client.send_message(query.message.chat.id, f"❌ Details not found for `{movie_query}`")

    except Exception as e:
        print(f"Person Movie View Error: {e}", flush=True)
