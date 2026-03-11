# Link Scraper

A Python web scraper that deep-crawls websites to extract structured download data. Uses Playwright for headless browser rendering, so it works with both static and JavaScript-heavy pages.

Supports site-specific parsers for accurate extraction of titles, dates, file sizes, and download URIs.

## Supported Sites

| Site | Parser |
|------|--------|
| FitGirl Repacks | `FitgirlParser` |
| SteamRip | `SteamRipParser` |
| Other sites | `GenericParser` (fallback) |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Scrape front page items (default: up to 50 items from 1 page)
python scraper.py https://fitgirl-repacks.site/

# Scrape multiple listing pages
python scraper.py https://fitgirl-repacks.site/ --max-pages 3

# Limit number of items
python scraper.py https://fitgirl-repacks.site/ --max-items 10

# Custom output path
python scraper.py https://fitgirl-repacks.site/ -o output/fitgirl.json
```

## Output Format

```json
{
  "name": "FitGirl Repacks",
  "downloads": [
    {
      "title": "Cities: Skylines - Collection, v1.21.1-f5 + 90 DLCs/Bonuses",
      "uploadDate": "2026-03-11T11:00:41+03:00",
      "fileSize": "9.9 GB",
      "uris": [
        "https://datanodes.to/.../file.part01.rar",
        "magnet:?xt=urn:btih:..."
      ]
    }
  ]
}
```

## Options

| Flag | Description |
|------|-------------|
| `url` | Target URL to scrape (required) |
| `-o, --output` | Output JSON file path (default: `output/downloads.json`) |
| `--max-pages N` | Max listing pages to crawl (default: 1) |
| `--max-items N` | Max items to scrape (default: 50) |

## Adding a New Site Parser

Subclass `SiteParser` in `scraper.py` and implement:
- `name()` - display name
- `matches(url)` - return `True` if this parser handles the URL
- `get_game_urls(soup, base_url)` - extract item page URLs from listing
- `parse_game_page(soup, url)` - extract structured data from item page
- `get_next_page(soup)` - (optional) return next listing page URL
