# Link Scraper

A Python web scraper that extracts download links from any website. Uses Playwright for headless browser rendering, so it works with both static and JavaScript-heavy pages.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Extract download links from a page
python scraper.py https://example.com/downloads

# Extract ALL links (not just downloads)
python scraper.py https://example.com --all-links

# Custom output file with pretty-printed JSON
python scraper.py https://example.com -o results.json --pretty

# Wait extra time for JS-heavy pages
python scraper.py https://example.com --wait 5
```

## Output Format

```json
{
  "source_url": "https://example.com/downloads",
  "total": 3,
  "links": [
    {
      "url": "https://example.com/file.zip",
      "text": "Download v2.0",
      "extension": ".zip",
      "is_download": true
    }
  ]
}
```

## Options

| Flag | Description |
|------|-------------|
| `url` | Target URL to scrape (required) |
| `-o, --output` | Output JSON file path (default: `links.json`) |
| `--all-links` | Extract all links, not just download links |
| `--wait N` | Extra seconds to wait for dynamic content |
| `--pretty` | Pretty-print JSON output |
