import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

BASE_URL = "https://en.wikipedia.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (CWL207 educational project)"}
REQUEST_DELAY = 1.5

MONTHS = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}

# Language sub-pages to scrape for each year
LANGUAGE_PAGES = [
    "List_of_Hindi_films_of_{year}",
    "List_of_Tamil_films_of_{year}",
    "List_of_Telugu_films_of_{year}",
    "List_of_Malayalam_films_of_{year}",
]


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
            x in h_lower for x in ["singer", "vocalist", "performed by", "artist"]
        ):
            col_map["singers"] = i
        elif "music_director" not in col_map and any(
            x in h_lower for x in ["music", "composer", "composed by"]
        ):
            col_map["music_director"] = i
        elif "lyricist" not in col_map and any(
            x in h_lower for x in ["lyric", "word", "written by"]
        ):
            col_map["lyricist"] = i
        elif "duration" not in col_map and any(
            x in h_lower for x in ["duration", "length", "time"]
        ):
            col_map["duration"] = i
    return col_map


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
    return bool(re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s.strip()))


def get_infobox_music_director(soup):
    """Extract the music director from the album/film infobox if present."""
    infobox = soup.find("table", class_=lambda c: c and "infobox" in " ".join(c))
    if not infobox:
        return ""
    for row in infobox.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            if any(kw in label for kw in ["music", "composer", "score"]):
                return cells[1].get_text(" ", strip=True)
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
    """Return URL of a dedicated soundtrack sub-page if linked via a hatnote."""
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if any(
            kw in heading.get_text(strip=True).lower()
            for kw in ["music", "soundtrack", "songs"]
        ):
            anchor = (
                heading.parent
                if "mw-heading" in heading.parent.get("class", [])
                else heading
            )
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
    return None


def scrape_film_songs(film_title, film_url, year):
    time.sleep(REQUEST_DELAY)
    soup = fetch_page(film_url)
    if not soup:
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
    years = [2022, 2023]
    max_films_per_year = 25  # per language (4 languages = up to 100 films total per year)
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
