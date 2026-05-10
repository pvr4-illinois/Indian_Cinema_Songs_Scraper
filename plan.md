# Indian Cinema Songs Scraper

## Project Goal
Scrape a list of songs for each Indian film from Wikipedia and save the data in CSV format.

## Our Specific Task
WIKIPEDIA: Scrape list of songs for each film and output in CSV format.

## Approach
1. Get a list of Indian films from Wikipedia
2. For each film, visit its Wikipedia page and scrape the soundtrack/songs table
3. Save everything to a CSV file

## Libraries to Use
- requests
- beautifulsoup4
- wikipedia-api
- pandas

## Output Format (CSV columns)
- film_name
- year
- song_name
- singer(s)
- music_director
- lyricist
- duration

## Output File
- songs.csv

## Notes
- Use BeautifulSoup to scrape Wikipedia pages
- Each Wikipedia film page usually has a "Soundtrack" or "Songs" table
- Need to handle cases where a film page has no songs table
- Add delays between requests to avoid getting blocked
- Push all changes to GitHub regularly using git add, git commit, git push
