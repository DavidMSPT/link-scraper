#!/usr/bin/env python3
"""Web scraper that extracts download links from websites.

Supports deep crawling: visits the homepage to find game/item pages,
then scrapes each individual page for structured download data.
"""

import argparse
import json
import re
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, Page

# Known file hosting domains whose links count as download URIs
DOWNLOAD_HOSTS = {
    "gofile.io", "buzzheavier.com", "vikingfile.com", "datanodes.to",
    "1fichier.com", "filecrypt.cc", "qiwi.gg", "pixeldrain.com",
    "mediafire.com", "mega.nz", "uploadhaven.com", "ddownload.com",
    "fuckingfast.co", "1337x.to", "rutor.info", "tapochek.net",
}


def is_download_uri(url: str) -> bool:
    """Check if a URL points to a file hosting service or direct download."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Strip www.
    host = host.removeprefix("www.")
    return host in DOWNLOAD_HOSTS or url.startswith("magnet:")


def fetch_page(page: Page, url: str, wait_ms: int = 3000, retries: int = 3) -> BeautifulSoup:
    """Navigate to a URL and return parsed HTML with retry on timeout."""
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(wait_ms)
            return BeautifulSoup(page.content(), "html.parser")
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 10
                print(f"    Retry {attempt + 1}/{retries - 1} after {wait}s: {e}")
                page.wait_for_timeout(wait * 1000)
            else:
                raise


# ---------------------------------------------------------------------------
# Site parsers
# ---------------------------------------------------------------------------

class SiteParser(ABC):
    """Base class for site-specific parsers."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def matches(self, url: str) -> bool:
        ...

    @abstractmethod
    def get_game_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract individual game page URLs from a listing page."""
        ...

    @abstractmethod
    def parse_game_page(self, soup: BeautifulSoup, url: str) -> dict | None:
        """Parse a single game page and return structured data."""
        ...

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        """Return URL for the next listing page, or None."""
        return None


class FitgirlParser(SiteParser):
    def name(self) -> str:
        return "FitGirl Repacks"

    def matches(self, url: str) -> bool:
        return "fitgirl-repacks" in url

    def get_game_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls = []
        for article in soup.find_all("article"):
            title_el = article.find(class_=re.compile(r"entry-title"))
            if not title_el:
                continue
            link = title_el.find("a", href=True)
            if link:
                href = link["href"]
                # Skip non-game posts (updates, announcements)
                if any(skip in href for skip in ["upcoming-repacks", "repack-updated", "donations"]):
                    continue
                urls.append(urljoin(base_url, href))
        return urls

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        nav = soup.find("nav", class_="pagination") or soup.find("nav", class_="navigation")
        if nav:
            next_link = nav.find("a", class_="next") or nav.find("a", string=re.compile(r"Next|→"))
            if next_link and next_link.get("href"):
                return next_link["href"]
        return None

    def parse_game_page(self, soup: BeautifulSoup, url: str) -> dict | None:
        # Title
        title_el = soup.find(class_=re.compile(r"entry-title"))
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # Upload date
        time_el = soup.find("time", datetime=True)
        upload_date = time_el["datetime"] if time_el else ""

        # File size - look for "Original Size:" or "Repack Size:"
        entry = soup.find(class_="entry-content")
        file_size = ""
        if entry:
            text = entry.get_text()
            # Prefer original size
            m = re.search(r"Original Size:\s*([\d.,]+\s*[GMKT]B)", text, re.IGNORECASE)
            if m:
                file_size = m.group(1).strip()
            else:
                m = re.search(r"Repack Size:\s*([\d.,]+[/\d.,]*\s*[GMKT]B)", text, re.IGNORECASE)
                if m:
                    file_size = m.group(1).strip()

        # Download URIs - all DDL parts + magnets
        uris = []
        seen = set()
        if entry:
            for a in entry.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href in seen:
                    continue

                if href.startswith("magnet:"):
                    seen.add(href)
                    uris.append(href)
                    continue

                parsed = urlparse(href)
                host = (parsed.hostname or "").removeprefix("www.")

                if host in DOWNLOAD_HOSTS:
                    seen.add(href)
                    uris.append(href)
                    continue

        if not uris:
            return None

        return {
            "title": title,
            "uploadDate": upload_date,
            "fileSize": file_size,
            "uris": uris,
        }


class SteamRipParser(SiteParser):
    def name(self) -> str:
        return "SteamRip"

    def matches(self, url: str) -> bool:
        return "steamrip" in url

    def get_game_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls = []
        for a in soup.select("a[href]"):
            href = a["href"]
            # SteamRip game pages typically have /game/ or end with -free-download
            if "-free-download" in href:
                full = urljoin(base_url, href)
                if full not in urls:
                    urls.append(full)
        return urls

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        next_link = soup.find("a", class_="next") or soup.find("a", string=re.compile(r"Next|→|›"))
        if next_link and next_link.get("href"):
            return next_link["href"]
        return None

    def parse_game_page(self, soup: BeautifulSoup, url: str) -> dict | None:
        title_el = soup.find("h1") or soup.find(class_=re.compile(r"entry-title|post-title"))
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        time_el = soup.find("time", datetime=True)
        upload_date = time_el["datetime"] if time_el else ""

        text = soup.get_text()
        file_size = ""
        m = re.search(r"File Size:\s*([\d.,]+\s*[GMKT]B)", text, re.IGNORECASE)
        if m:
            file_size = m.group(1).strip()

        uris = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if is_download_uri(href) and href not in seen:
                seen.add(href)
                uris.append(href)

        if not uris:
            return None

        return {
            "title": title,
            "uploadDate": upload_date,
            "fileSize": file_size,
            "uris": uris,
        }


class GenericParser(SiteParser):
    """Fallback parser that extracts any download-looking links."""

    def name(self) -> str:
        host = "Unknown"
        return host

    def matches(self, url: str) -> bool:
        return True  # Fallback

    def get_game_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            parsed = urlparse(href)
            base_parsed = urlparse(base_url)
            # Same-domain links with path depth > 1
            if parsed.hostname == base_parsed.hostname and parsed.path.count("/") > 1:
                if href not in urls:
                    urls.append(href)
        return urls

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        next_link = soup.find("a", class_="next") or soup.find("a", rel="next")
        if next_link and next_link.get("href"):
            return next_link["href"]
        return None

    def parse_game_page(self, soup: BeautifulSoup, url: str) -> dict | None:
        title_el = soup.find("h1")
        title = title_el.get_text(strip=True) if title_el else urlparse(url).path

        time_el = soup.find("time", datetime=True)
        upload_date = time_el["datetime"] if time_el else ""

        uris = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if is_download_uri(href) and href not in seen:
                seen.add(href)
                uris.append(href)

        if not uris:
            return None

        return {
            "title": title,
            "uploadDate": upload_date,
            "fileSize": "",
            "uris": uris,
        }


PARSERS = [FitgirlParser(), SteamRipParser(), GenericParser()]


def get_parser(url: str) -> SiteParser:
    for parser in PARSERS:
        if parser.matches(url):
            return parser
    return GenericParser()


def save_progress(output_path: Path, site_name: str, downloads: list[dict]):
    """Save current progress to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"name": site_name, "downloads": downloads}, f, indent=2)


def scrape_site(url: str, max_pages: int, max_items: int, output_path: Path | None = None) -> dict:
    """Scrape a site: list pages -> individual item pages -> structured data."""
    parser = get_parser(url)
    site_name = parser.name()
    print(f"Using parser: {site_name}")

    downloads = []
    pages_scraped = 0
    current_url = url

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while current_url and pages_scraped < max_pages:
            pages_scraped += 1
            print(f"\n[Page {pages_scraped}] {current_url}")

            try:
                soup = fetch_page(page, current_url)
            except Exception as e:
                print(f"  Failed to load listing page: {e}")
                print(f"  Skipping to next page...")
                # Try to construct the next page URL manually
                current_url = re.sub(r"/page/\d+/", f"/page/{pages_scraped + 1}/", current_url)
                if f"/page/" not in current_url:
                    current_url = url.rstrip("/") + f"/page/{pages_scraped + 1}/"
                continue

            game_urls = parser.get_game_urls(soup, current_url)
            print(f"  Found {len(game_urls)} item links")

            for i, game_url in enumerate(game_urls):
                if len(downloads) >= max_items:
                    break

                print(f"  [{i+1}/{len(game_urls)}] Scraping {game_url[:80]}...")
                try:
                    game_soup = fetch_page(page, game_url, wait_ms=2000)
                    result = parser.parse_game_page(game_soup, game_url)
                    if result:
                        downloads.append(result)
                        print(f"    -> {result['title'][:60]} ({result['fileSize']}, {len(result['uris'])} URIs)")
                    else:
                        print(f"    -> No download links found, skipping")
                except Exception as e:
                    print(f"    -> Error: {e}")

            # Save progress after each page
            if output_path and downloads:
                save_progress(output_path, site_name, downloads)

            if len(downloads) >= max_items:
                print(f"\nReached max items limit ({max_items})")
                break

            current_url = parser.get_next_page(soup)

        browser.close()

    return {"name": site_name, "downloads": downloads}


def main():
    parser = argparse.ArgumentParser(
        description="Scrape download links from a website with deep crawling."
    )
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument(
        "-o", "--output",
        default="output/downloads.json",
        help="Output JSON file path (default: output/downloads.json)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Max listing pages to crawl (default: 1)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=50,
        help="Max items to scrape (default: 50)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Overwrite output file instead of merging with existing data",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = scrape_site(args.url, args.max_pages, args.max_items, output_path)

    # Merge with existing data unless --fresh is specified
    if not args.fresh and output_path.exists():
        with open(output_path) as f:
            existing = json.load(f)
        existing_titles = {d["title"] for d in existing.get("downloads", [])}
        new_items = [d for d in result["downloads"] if d["title"] not in existing_titles]
        # Prepend new items (most recent first)
        result["downloads"] = new_items + existing["downloads"]
        print(f"\nMerged {len(new_items)} new items with {len(existing['downloads'])} existing.")

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nDone! {len(result['downloads'])} total items in output.")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
