"""Scheduled pipeline entry point.

Triggered daily at 09:00 by launchd (see launchd/com.apartmentscraper.plist).
Scrapes all configured sources, scores and filters listings against saved config,
persists results to SQLite, and sends unseen listings via Telegram.

Run manually: `uv run src/pipeline.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from database import init_db, mark_notified, upsert_listing, get_unsent_listings
from notifier import send_listings
from scorer import score_and_filter
from scrapers import scrape_all


def run() -> None:
    """Execute the full scrape → score → save → notify pipeline."""
    print("=== Apartment Scout pipeline starting ===")
    init_db()

    print("Scraping all sources...")
    raw_listings = scrape_all()
    print(f"  Found {len(raw_listings)} listings after dedup")

    print("Scoring and filtering...")
    scored = score_and_filter(raw_listings)
    print(f"  {len(scored)} listings passed filters")

    for listing in scored:
        upsert_listing(listing)

    new_listings = get_unsent_listings()
    print(f"  {len(new_listings)} new listings to notify")

    print("Sending Telegram notification...")
    send_listings(new_listings)

    if new_listings:
        mark_notified([(listing["id"], listing["source"]) for listing in new_listings])

    print("=== Pipeline complete ===")


if __name__ == "__main__":
    run()
