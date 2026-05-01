import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time


#GLOBAL VARIABLES - YOU CAN DEFINE THIS HOW YOU SEE FIT
MIN_YEAR=2022
#Year preferably later (>2000) rather than earlier
MAX_YEAR=2026
#MAX_YEAR must be greater than MIN_YEAR

MAX_FILMS_PER_YEAR_PER_LANGUAGE=1000
#1000 means scrape all possible films for the language, set to a number between 10-100 if you want a limited number of each language
# Language sub-pages to scrape for each year, REMOVE HASHTAGS FOR MORE LANGUAGES!
LANGUAGE_PAGES = [
    "List_of_Hindi_films_of_{year}",
    "List_of_Tamil_films_of_{year}",
    "List_of_Telugu_films_of_{year}",
    "List_of_Malayalam_films_of_{year}",
    "List_of_Kannada_films_of_{year}",
    #"List_of_Marathi_films_of_{year}",
    #"List_of_Gujarati_films_of_{year}",
    #"List_of_Indian_Bengali_films_of_{year}",
    #"List_of_Punjabi_films_of_{year}",

    #Below were available for some years
    #"List_of_Bhojpuri_films_of_{year}",
    #"List_of_Assamese_films_of_{year}",
    #"List_of_Tulu_films_of_{year}",
]


#END OF USERDESIGNED VARS!

BASE_URL = "https://en.wikipedia.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (CWL207 educational project)"}
REQUEST_DELAY = 1.1

MONTHS = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}



def fetch_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  Error fetching {url}: {e}")
        return None


def find_film_link_in_row(row):
    """Return (title, url) of the film linked in this table row, or (None, None)."""
    for cell in row.find_all(["td", "th"]):
        text = cell.get_text(strip=True)
        # Skip day numbers, month names, very short strings, ref cells
        if re.match(r"^\d{1,2}$", text):
            continue
        if text.lower() in MONTHS:
            continue
        if len(text) < 3:
            continue
        link = cell.find("a", href=True)
        if link and link["href"].startswith("/wiki/") and ":" not in link["href"]:
            return link.get_text(strip=True), BASE_URL + link["href"]
    return None, None


def get_films_for_year(year, max_per_language=25):
    films = []
    seen_urls = set()

    for page_template in LANGUAGE_PAGES:
        page_name = page_template.format(year=year)
        url = f"{BASE_URL}/wiki/{page_name}"
        soup = fetch_page(url)
        if not soup:
            continue
        time.sleep(REQUEST_DELAY)

        for table in soup.find_all("table", class_="wikitable"):
            rows = table.find_all("tr")[1:]
            for row in rows:
                title, film_url = find_film_link_in_row(row)
                if title and film_url and film_url not in seen_urls:
                    seen_urls.add(film_url)
                    films.append({"title": title, "url": film_url, "year": year})
                    if len([f for f in films if f["year"] == year]) >= max_per_language * len(LANGUAGE_PAGES):
                        break

    return films


def map_headers(headers):
    col_map = {}
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if "song_name" not in col_map and any(
            x in h_lower for x in ["song", "title", "track", "name"]
        ):
            col_map["song_name"] = i
        elif "singers" not in col_map and any(
            x in h_lower for x in ["singer", "vocalist", "performed by", "artist", "singer(s)"]
        ):
            col_map["singers"] = i
        elif "music_director" not in col_map and any(
            x in h_lower for x in ["music", "composer", "composed by"]
        ):
            col_map["music_director"] = i
        elif "lyricist" not in col_map and any(
            x in h_lower for x in ["lyric", "word", "written by", "lyrics"]
        ):
            col_map["lyricist"] = i
        elif "duration" not in col_map and any(
            x in h_lower for x in ["duration", "length", "time"]
        ):
            col_map["duration"] = i
    return col_map


def page_has_film_category(soup):
    cat_links = soup.find("div", id="mw-normal-catlinks")
    if not cat_links:
        return True
    
    cat_text = cat_links.get_text(" ", strip=True).lower()
    
    is_person = "living people" in cat_text or "births" in cat_text#tags associated with people
    is_film = any(kw in cat_text for kw in [
        "language films", "indian films", "directed by", "film based on",
        "films set in", "hindi films", "tamil films", "telugu films",
        "malayalam films", "kannada films", "marathi films", "punjabi films",
        "gujarati films", "bengali films"#tags that are going to be associated with films found in the metadata
    ])
    
    # IF its clearly a person and NOT a film we can return it, otherwise we want to be save to prevent false negatives
    if is_person and not is_film:
        return False
    
    return True

def is_song_table(headers_lower):
    has_title = any(
        any(kw in h for kw in ["song", "title", "track"]) for h in headers_lower
    )
    has_meta = any(
        any(kw in h for kw in ["singer", "music", "composer", "lyric", "length", "duration"])
        for h in headers_lower
    )
    return has_title and has_meta


def is_duration_string(s):
    """Return True if s looks like a total-duration timestamp (e.g. '29:36', '1:02:45')."""
    s_compact = s.replace(" ", "")
    return bool(re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s_compact.strip()))
#this was changed to caputre lengths like "9 : 00" which appeared a couple times


def get_infobox_music_director(soup):
    """Extract the music director from the film/album infobox if present."""
    infobox = soup.find("table", class_="infobox")
    if not infobox:
        return ""
    for row in infobox.find_all("tr"):
        label_cell = row.find("th")
        value_cell = row.find("td")
        if not label_cell or not value_cell:
            continue
        label = label_cell.get_text(" ", strip=True).lower()
        if any(kw in label for kw in ["music", "composer", "score"]):
            value = value_cell.get_text(", ", strip=True)
            # Strip trailing footnote brackets like [1][2]
            return re.sub(r"\[\d+\]", "", value).strip(" ,")
    return ""


def parse_song_table(table, film_title, year, fallback_music_director=""):
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    raw_headers = [h.get_text(strip=True) for h in rows[0].find_all(["th", "td"])]
    headers_lower = [h.lower() for h in raw_headers]

    if not is_song_table(headers_lower):
        return []

    col_map = map_headers(raw_headers)

    # Strip smart quotes + ASCII double quote that Wikipedia wraps song titles with
    _quote_table = str.maketrans({0x201C: None, 0x201D: None,
                                   0x2018: None, 0x2019: None,
                                   0x22: None})

    def get_cell(cells, key):
        idx = col_map.get(key)
        if idx is not None and idx < len(cells):
            text = cells[idx].get_text(" ", strip=True)
            text = text.translate(_quote_table).strip().strip("'").strip()
            return text
        return ""

    songs = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        song_name = get_cell(cells, "song_name")
        if not song_name:
            continue
        # Skip total / summary rows
        if song_name.lower().startswith("total") or is_duration_string(song_name):
            continue
#trying to fix bug with total values of soundtrack length being represented as actual sound 
        if any(kw in song_name.lower() for kw in ["songs:", "background score:", "score:", "music:"]):
            continue

        music_dir = get_cell(cells, "music_director") or fallback_music_director

        songs.append(
            {
                "film_name": film_title,
                "year": year,
                "song_name": song_name,
                "singer(s)": get_cell(cells, "singers"),
                "music_director": music_dir,
                "lyricist": get_cell(cells, "lyricist"),
                "duration": get_cell(cells, "duration"),
            }
        )

    return songs


def find_soundtrack_link(soup):
    # Original heading-based search first
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if any(kw in heading.get_text(strip=True).lower() for kw in ["music", "soundtrack", "songs"]):
            anchor = heading.parent if "mw-heading" in heading.parent.get("class", []) else heading
            for sib in anchor.find_next_siblings():
                if "mw-heading" in sib.get("class", []):
                    break
                if hasattr(sib, "find"):
                    hatnote = sib.find("div", class_="hatnote")
                    if hatnote:
                        link = hatnote.find("a", href=True)
                        if link and "/wiki/" in link["href"]:
                            return BASE_URL + link["href"]
                if sib.name == "p":
                    break

    # scanning all hatnotes instead of what we were doing previously
    for hatnote in soup.find_all("div", class_="hatnote"):
        text = hatnote.get_text(strip=True).lower()
        if any(kw in text for kw in ["soundtrack", "music", "songs"]):
            link = hatnote.find("a", href=True)
            if link and "/wiki/" in link["href"]:
                return BASE_URL + link["href"]

    return None

def scrape_film_songs(film_title, film_url, year):
    time.sleep(REQUEST_DELAY)
    soup = fetch_page(film_url)
    if not soup:
        return []
    
    if not page_has_film_category(soup):
        print(f"    (skipping — person page)")#explicitly marking it, the issue beforehand was that we had a lot of director/actor pages being scraped (their discographies would get added as songs)
        return []

    fallback_md = get_infobox_music_director(soup)

    # Try tables on the film page first
    for t in soup.find_all("table"):
        classes = " ".join(t.get("class", []))
        if "wikitable" in classes or "tracklist" in classes:
            songs = parse_song_table(t, film_title, year, fallback_md)
            if songs:
                return songs

    # Follow hatnote link to dedicated soundtrack page
    soundtrack_url = find_soundtrack_link(soup)
    if soundtrack_url:
        time.sleep(REQUEST_DELAY)
        sub_soup = fetch_page(soundtrack_url)
        if sub_soup:
            sub_md = get_infobox_music_director(sub_soup) or fallback_md
            for t in sub_soup.find_all("table"):
                classes = " ".join(t.get("class", []))
                if "wikitable" in classes or "tracklist" in classes:
                    songs = parse_song_table(t, film_title, year, sub_md)
                    if songs:
                        return songs

    return []


def main():
    years=[]
    for i in range(MIN_YEAR, MAX_YEAR+1):
        years.append(i)
    max_films_per_year = MAX_FILMS_PER_YEAR_PER_LANGUAGE  # for testing
    all_songs = []

    for year in years:
        print(f"\n=== Year {year} ===")
        films = get_films_for_year(year, max_per_language=max_films_per_year)
        print(f"Found {len(films)} unique films across languages. Scraping...")

        for i, film in enumerate(films):
            print(f"  [{i+1:3d}/{len(films)}] {film['title']}", end=" ... ", flush=True)
            songs = scrape_film_songs(film["title"], film["url"], film["year"])
            if songs:
                print(f"{len(songs)} songs")
                all_songs.extend(songs)
            else:
                print("no songs table")

    if all_songs:
        df = pd.DataFrame(all_songs)
        df = df[
            [
                "film_name",
                "year",
                "song_name",
                "singer(s)",
                "music_director",
                "lyricist",
                "duration",
            ]
        ]
        df.to_csv("songs.csv", index=False, encoding="utf-8-sig")
        print(
            f"\nSaved {len(all_songs)} songs from {df['film_name'].nunique()} films to songs.csv"
        )
    else:
        print("\nNo songs data found.")


if __name__ == "__main__":
    main()