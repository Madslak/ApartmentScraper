"""Boligsiden.dk scraper.

Uses Playwright to render each search-results page and regex to extract
structured listing data — no fragile CSS selectors, no external LLM calls.

One browser page is opened per postal code (up to CONCURRENCY in parallel).
Neighborhood is inferred from the postal code so the caller gets it for free.
"""

import asyncio
import json
import re

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

BASE_URL = "https://www.boligsiden.dk/postnummer/{zip}/tilsalg/ejerlejlighed?areaMin=50&priceMax=5500000"

NEIGHBORHOOD_ZIPS: dict[str, list[int]] = {
    "Nørrebro":      [2200],
    "Frederiksberg": [2000],
    "Indre By":      [1050, 1100, 1150, 1200, 1250, 1300, 1350, 1400, 1450],
    "Vesterbro":     [1500, 1550, 1600, 1620, 1650, 1700, 1750, 1800],
    "Østerbro":      [2100],
    "Amager":        [2300, 2450],
    "Valby":         [2500],
}

HEADERS = {
    "Accept-Language": "da-DK,da;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

CONCURRENCY = 4


async def _dismiss_consent(page) -> None:
    """Click whichever cookie consent button is present, if any."""
    for text in ["Afvis og luk", "Accepter og luk", "Accepter alle"]:
        try:
            btn = page.get_by_text(text, exact=True)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


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
        await _dismiss_consent(page)
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


async def _scrape_all() -> list[dict]:
    """Scrape all configured neighborhoods in parallel and deduplicate by listing ID."""
    tasks_input = [
        (nb, z)
        for nb, zips in NEIGHBORHOOD_ZIPS.items()
        for z in zips
    ]
    all_listings: list[dict] = []
    seen_ids: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def bounded(nb: str, z: int) -> list[dict]:
            async with semaphore:
                try:
                    results = await _scrape_zip_new_page(browser, z, nb)
                    if results:
                        print(f"  {nb} ({z}): {len(results)} listings")
                    return results
                except Exception as e:
                    print(f"  {nb} ({z}): error — {e}")
                    return []

        batches = await asyncio.gather(*[bounded(nb, z) for nb, z in tasks_input])
        await browser.close()

    for batch in batches:
        for listing in batch:
            if listing["id"] not in seen_ids:
                seen_ids.add(listing["id"])
                all_listings.append(listing)

    return all_listings


def scrape_boligsiden() -> list[dict]:
    """Entry point: scrape Boligsiden.dk and return a flat list of listing dicts."""
    return asyncio.run(_scrape_all())


if __name__ == "__main__":
    listings = scrape_boligsiden()
    print(json.dumps(listings[:3], indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(listings)} listings")
