#!/usr/bin/env python3
"""Web scraper that extracts download links from a given URL."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DOWNLOAD_EXTENSIONS = {
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".tgz",
    # Executables / installers
    ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage", ".snap",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".odt",
    # Media
    ".mp3", ".mp4", ".avi", ".mkv", ".wav", ".flac", ".mov", ".wmv",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".bmp", ".webp", ".tiff",
    # Data
    ".json", ".xml", ".yaml", ".yml", ".sql", ".db", ".sqlite",
    # Code / dev
    ".whl", ".jar", ".war", ".apk", ".ipa", ".iso", ".img", ".bin",
}


def is_download_link(url: str) -> bool:
    """Check if a URL likely points to a downloadable file."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in DOWNLOAD_EXTENSIONS)


def extract_links(html: str, base_url: str, download_only: bool) -> list[dict]:
    """Extract links from HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        absolute_url = urljoin(base_url, href)

        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        text = anchor.get_text(strip=True) or ""
        is_download = is_download_link(absolute_url)

        # Check for download attribute on the anchor tag
        has_download_attr = anchor.has_attr("download")

        if download_only and not is_download and not has_download_attr:
            continue

        parsed = urlparse(absolute_url)
        ext = Path(parsed.path).suffix.lower() if parsed.path else ""

        links.append({
            "url": absolute_url,
            "text": text,
            "extension": ext,
            "is_download": is_download or has_download_attr,
        })

    return links


def scrape(url: str, download_only: bool, wait_seconds: int) -> list[dict]:
    """Scrape a URL using a headless browser and extract links."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"Navigating to {url} ...")
        page.goto(url, wait_until="networkidle", timeout=60000)

        if wait_seconds > 0:
            print(f"Waiting {wait_seconds}s for dynamic content ...")
            page.wait_for_timeout(wait_seconds * 1000)

        html = page.content()
        final_url = page.url
        browser.close()

    return extract_links(html, final_url, download_only)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape download links from a website."
    )
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument(
        "-o", "--output",
        default="links.json",
        help="Output JSON file path (default: links.json)",
    )
    parser.add_argument(
        "--all-links",
        action="store_true",
        help="Extract all links, not just download links",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        help="Extra seconds to wait for dynamic content (default: 0)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output",
    )

    args = parser.parse_args()
    download_only = not args.all_links

    links = scrape(args.url, download_only, args.wait)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    indent = 2 if args.pretty else None
    with open(output_path, "w") as f:
        json.dump({"source_url": args.url, "total": len(links), "links": links}, f, indent=indent)

    print(f"Found {len(links)} {'links' if args.all_links else 'download links'}.")
    print(f"Results saved to {output_path}")

    if not links:
        mode_hint = "" if args.all_links else " Try --all-links to see all links."
        print(f"No links found.{mode_hint}")


if __name__ == "__main__":
    main()
