"""Multi-source scraper entry point.

scrape_all() runs all scrapers sharing one browser instance, then deduplicates
by canonical address key. Realtor-site listings overwrite Boligsiden duplicates
(Boligsiden is an aggregator, so the original site version is preferred).
"""

import asyncio

from playwright.async_api import async_playwright

from .base import canonical_key
from . import boligsiden, danbolig, edc, home, nybolig

# Order matters: boligsiden goes first so realtor-site results overwrite it
_SCRAPERS = [
    ("boligsiden", boligsiden.scrape_with_browser),
    ("nybolig", nybolig.scrape_with_browser),
    ("home", home.scrape_with_browser),
    ("edc", edc.scrape_with_browser),
    ("danbolig", danbolig.scrape_with_browser),
]


async def _scrape_all_async() -> list[dict]:
    """Run all scrapers concurrently sharing one browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [fn(browser) for _, fn in _SCRAPERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    all_listings: list[dict] = []
    for (name, _), result in zip(_SCRAPERS, results):
        if isinstance(result, Exception):
            print(f"  [{name}] scraper failed: {result}")
        else:
            all_listings.extend(result)

    return all_listings


def _dedup(listings: list[dict]) -> list[dict]:
    """One entry per physical address. Later entries overwrite earlier ones.

    Since _SCRAPERS lists boligsiden first, realtor sites overwrite it when
    the same apartment appears on both (seen[key] = listing is last-writer-wins).
    Listings without a usable address key are kept as-is (keyed by id+source).
    """
    seen: dict[str, dict] = {}
    for listing in listings:
        key = canonical_key(listing)
        if not key:
            key = f"{listing.get('source', '')}_{listing.get('id', '')}"
        seen[key] = listing
    return list(seen.values())


def scrape_all() -> list[dict]:
    """Scrape all sources and return a deduplicated list of listings."""
    raw = asyncio.run(_scrape_all_async())
    deduped = _dedup(raw)
    print(f"  Scraped {len(raw)} total, {len(deduped)} after dedup")
    return deduped
