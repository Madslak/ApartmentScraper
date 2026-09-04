"""Scheduled pipeline entry point.

Triggered daily at 09:00 by launchd (see launchd/com.apartmentscraper.plist).
Scrapes all configured sources, scores and filters listings against saved config,
persists results to SQLite, and sends unseen listings via Telegram.

Run manually: `uv run src/pipeline.py`
"""

import socket
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from database import init_db, mark_notified, upsert_listing, get_unsent_listings
from notifier import send_listings
from scorer import score_and_filter
from scrapers import scrape_all


def wait_for_network(timeout: int = 300, interval: int = 10) -> bool:
    """Block until DNS + connectivity is up, or until ``timeout`` seconds elapse.

    launchd fires a missed 09:00 job the moment the Mac wakes, often before
    Wi-Fi/DNS have reconnected — which previously crashed the run with
    ERR_INTERNET_DISCONNECTED / "nodename nor servname provided". This polls a
    couple of the hosts we actually depend on and returns True once one is
    reachable, or False if still offline after ``timeout``.
    """
    hosts = [("api.telegram.org", 443), ("www.boligsiden.dk", 443)]
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        for host, port in hosts:
            try:
                with socket.create_connection((host, port), timeout=5):
                    print(f"  Network is up (reached {host} on attempt {attempt}).")
                    return True
            except OSError:
                continue
        if time.monotonic() >= deadline:
            print(f"  Network still unreachable after {timeout}s — aborting.")
            return False
        print(f"  Network not ready (attempt {attempt}); retrying in {interval}s...")
        time.sleep(interval)


def run() -> None:
    """Execute the full scrape → score → save → notify pipeline."""
    started = datetime.now().astimezone()
    print(f"=== Apartment Scout pipeline starting {started:%Y-%m-%d %H:%M:%S %Z} ===")

    print("Waiting for network...")
    if not wait_for_network():
        print("=== Pipeline aborted: no network ===")
        sys.exit(1)

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

    finished = datetime.now().astimezone()
    elapsed = int((finished - started).total_seconds())
    print(f"=== Pipeline complete {finished:%Y-%m-%d %H:%M:%S %Z} ({elapsed}s) ===")


if __name__ == "__main__":
    run()
