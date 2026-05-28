"""Nybolig.dk scraper.

Searches ejerlejligheder in the Capital Region and filters locally to our
target Copenhagen zip codes. Uses Playwright because the site is JS-rendered.

Card structure (div.property-search__results-item):
  Text: "{address1} {address2} {price} kr. | Ejerlejlighed | {rooms} vær. | {size} m2 |"
  Link: a.o-tile__link → /ejerlejlighed/{zip}/{street}/{id1}/{caseid}
"""

import asyncio
import re

from playwright.async_api import async_playwright

from .base import CONCURRENCY, HEADERS, dismiss_consent, neighborhood_for_zip

# Capital Region search — we filter to target zips locally
SEARCH_URL = (
    "https://www.nybolig.dk/til-salg/ejerlejlighed/region-hovedstaden"
    "?areaMin=50&priceMax=5500000"
)
NEXT_PAGE_URL = SEARCH_URL + "&page={page}"

CARD_SELECTOR = "div.property-search__results-item"


def _parse_card(text: str, href: str) -> dict | None:
    """Parse a Nybolig listing card.

    Returns None if the listing zip is not in our target neighborhoods or
    if price/size are missing.
    """
    # Extract zip from address (4-digit number not part of price)
    # Price numbers are typically 6-7 digits; zip is exactly 4
    zip_matches = re.findall(r"\b(\d{4})\b", text)
    zip_code = int(zip_matches[0]) if zip_matches else 0
    neighborhood = neighborhood_for_zip(zip_code)
    if not neighborhood:
        return None  # Not a target zip

    # Price: "{digits with dots} kr."
    price_m = re.search(r"([\d.]+)\s*kr\.", text)
    if not price_m:
        return None
    price = int(price_m.group(1).replace(".", ""))

    # Size: "{number} m2"
    size_m = re.search(r"(\d+(?:[,.]\d+)?)\s*m2\b", text)
    size = float(size_m.group(1).replace(",", ".")) if size_m else 0.0

    # Rooms: "{number} vær."
    rooms_m = re.search(r"(\d+)\s*vær\.", text)
    rooms = int(rooms_m.group(1)) if rooms_m else 0

    # Address: first line with a 4-digit zip, stripping the "Ejerlejlighed: " prefix
    address = ""
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        if re.search(r"\b\d{4}\b", line) and "kr" not in line.lower() and "m2" not in line.lower():
            # Strip "Ejerlejlighed: " or similar type prefix
            line = re.sub(r"^[A-ZÆØÅ][^:]+:\s*", "", line)
            address = line
            break

    # Listing ID: last path segment of the href
    listing_id = href.strip("/").split("/")[-1] if href else ""
    if not listing_id or not price or not size:
        return None

    return {
        "id": listing_id,
        "source": "nybolig",
        "url": f"https://www.nybolig.dk{href}",
        "title": address,
        "price": price,
        "size": size,
        "rooms": rooms,
        "neighborhood": neighborhood,
        "address": address,
    }


async def _scrape_page(page, url: str, consent_dismissed: list) -> list[dict]:
    """Load one search results page and extract all matching listings."""
    await page.goto(url, wait_until="networkidle", timeout=35000)
    await page.wait_for_timeout(2000)

    if not consent_dismissed:
        await dismiss_consent(page)
        await page.wait_for_timeout(1000)
        consent_dismissed.append(True)

    cards = await page.query_selector_all(CARD_SELECTOR)
    listings = []
    for card in cards:
        try:
            text = await card.inner_text()
            link_el = await card.query_selector("a.o-tile__link")
            href = await link_el.get_attribute("href") if link_el else ""
            parsed = _parse_card(text, href)
            if parsed:
                listings.append(parsed)
        except Exception:
            continue
    return listings


async def scrape_with_browser(browser) -> list[dict]:
    """Scrape Nybolig Capital Region listings and return target-zip apartments."""
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.set_extra_http_headers(HEADERS)
    consent_dismissed: list = []
    all_listings: list[dict] = []
    seen_ids: set[str] = set()

    try:
        # First page
        results = await _scrape_page(page, SEARCH_URL, consent_dismissed)
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_listings.append(r)
        print(f"  [nybolig] page 1: {len(results)} cards, {len(all_listings)} in target area")

        # Continue paginating until no new results or max 10 pages
        for page_num in range(2, 11):
            paged = await _scrape_page(page, NEXT_PAGE_URL.format(page=page_num), consent_dismissed)
            if not paged:
                break
            added = 0
            for r in paged:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_listings.append(r)
                    added += 1
            print(f"  [nybolig] page {page_num}: {len(paged)} cards, {added} new in target area")
            if added == 0:
                break  # No new target-area listings, stop paginating
    except Exception as e:
        print(f"  [nybolig] error: {e}")
    finally:
        await page.close()

    return all_listings


def scrape_nybolig() -> list[dict]:
    """Standalone entry point."""
    async def _run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            results = await scrape_with_browser(browser)
            await browser.close()
            return results
    return asyncio.run(_run())


if __name__ == "__main__":
    import json
    listings = scrape_nybolig()
    print(json.dumps(listings[:3], indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(listings)}")
