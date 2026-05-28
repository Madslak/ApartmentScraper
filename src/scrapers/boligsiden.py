"""Boligsiden.dk scraper.

Uses Playwright to render each search-results page and regex to extract
structured listing data — no fragile CSS selectors, no external LLM calls.

One browser page is opened per postal code (up to CONCURRENCY in parallel).
Neighborhood is inferred from the postal code so the caller gets it for free.
"""

import asyncio
import json
import re

from playwright.async_api import async_playwright

from .base import CONCURRENCY, HEADERS, NEIGHBORHOOD_ZIPS, dismiss_consent

BASE_URL = "https://www.boligsiden.dk/postnummer/{zip}/tilsalg/ejerlejlighed?areaMin=50&priceMax=5500000"


def _parse_card_text(text: str, href: str, neighborhood: str) -> dict | None:
    """Parse the inner text of a [data-testid='case-list-card'] element.

    Boligsiden card text follows a predictable structure:
        3.995.000 kr.
        Ejerlejlighed | M² pris ...
        Gormsgade 10, st. 59., 2200 København N   ← address line (contains zip)
        64 m²
        2 vær.
        ...
    Returns None if price or size cannot be determined.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    price = 0
    for line in lines:
        m = re.match(r"^([\d.]+)\s*kr\.", line)
        if m:
            price = int(m.group(1).replace(".", ""))
            break

    sizes = re.findall(r"(\d+(?:,\d+)?)\s*m²", text)
    size = float(sizes[0].replace(",", ".")) if sizes else 0.0

    rooms = 0
    m = re.search(r"(\d+)\s*vær\.", text)
    if m:
        rooms = int(m.group(1))

    address = ""
    for line in lines:
        if re.search(r"\b\d{4}\b", line) and "kr" not in line.lower() and "m²" not in line:
            address = line
            break

    listing_id = href.strip("/").split("/")[-1]

    if not price or not size:
        return None

    return {
        "id": listing_id,
        "source": "boligsiden",
        "url": f"https://www.boligsiden.dk{href}",
        "title": address,
        "price": price,
        "size": size,
        "rooms": rooms,
        "neighborhood": neighborhood,
        "address": address,
    }


async def _scrape_zip(page, zip_code: int, neighborhood: str, consent_dismissed: list) -> list[dict]:
    """Load one postal code search page and return all parsed listing dicts."""
    url = BASE_URL.format(zip=zip_code)
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1500)

    if not consent_dismissed:
        await dismiss_consent(page)
        await page.wait_for_timeout(500)
        consent_dismissed.append(True)

    cards = await page.query_selector_all("[data-testid='case-list-card']")
    listings = []
    for card in cards:
        try:
            text = await card.inner_text()
            link = await card.query_selector("a[href*='/adresse/']")
            href = await link.get_attribute("href") if link else ""
            parsed = _parse_card_text(text, href, neighborhood)
            if parsed:
                listings.append(parsed)
        except Exception:
            continue
    return listings


async def _scrape_zip_new_page(browser, zip_code: int, neighborhood: str) -> list[dict]:
    """Open a fresh browser page, scrape one zip code, then close the page."""
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.set_extra_http_headers(HEADERS)
    consent_dismissed: list = []
    try:
        return await _scrape_zip(page, zip_code, neighborhood, consent_dismissed)
    finally:
        await page.close()


async def scrape_with_browser(browser) -> list[dict]:
    """Scrape all configured neighborhoods using the given browser. Deduplicates by listing ID."""
    tasks_input = [
        (nb, z)
        for nb, zips in NEIGHBORHOOD_ZIPS.items()
        for z in zips
    ]
    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def bounded(nb: str, z: int) -> list[dict]:
        async with semaphore:
            try:
                results = await _scrape_zip_new_page(browser, z, nb)
                if results:
                    print(f"  [boligsiden] {nb} ({z}): {len(results)} listings")
                return results
            except Exception as e:
                print(f"  [boligsiden] {nb} ({z}): error — {e}")
                return []

    batches = await asyncio.gather(*[bounded(nb, z) for nb, z in tasks_input])

    for batch in batches:
        for listing in batch:
            if listing["id"] not in seen_ids:
                seen_ids.add(listing["id"])
                all_listings.append(listing)

    return all_listings


def scrape_boligsiden() -> list[dict]:
    """Entry point: scrape Boligsiden.dk standalone (owns its own browser)."""
    async def _run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            results = await scrape_with_browser(browser)
            await browser.close()
            return results
    return asyncio.run(_run())


if __name__ == "__main__":
    listings = scrape_boligsiden()
    print(json.dumps(listings[:3], indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(listings)} listings")
