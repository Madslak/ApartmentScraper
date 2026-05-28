"""Home.dk scraper.

Searches lejligheder (apartments) in the Capital Region and filters locally
to our target Copenhagen zip codes. Nuxt.js SPA — requires Playwright.

Card structure (div.property-card):
  Text: "[Nyhed] {address} Lejlighed {size} m2 {price} kr."
  Link: a[href^='/salg/lejligheder/'] → /salg/lejligheder/{slug}/sag-{id}/
  Note: room count is NOT shown on listing cards — defaults to 0.
"""

import asyncio
import re

from playwright.async_api import async_playwright

from .base import HEADERS, dismiss_consent, neighborhood_for_zip

SEARCH_URL = "https://home.dk/til-salg/lejlighed/region-hovedstaden/"
NEXT_PAGE_URL = SEARCH_URL + "?page={page}"

CARD_SELECTOR = "div.property-card"


def _parse_card(text: str, href: str) -> dict | None:
    """Parse a Home.dk listing card.

    Home shows: {address}, Lejlighed, {size} m2, {price} kr.
    No room count on cards — defaults to 0.
    """
    # Extract zip from address (4-digit number)
    zip_matches = re.findall(r"\b(\d{4})\b", text)
    zip_code = int(zip_matches[0]) if zip_matches else 0
    neighborhood = neighborhood_for_zip(zip_code)
    if not neighborhood:
        return None

    # Price: "{digits with dots} kr."
    price_m = re.search(r"([\d.]+)\s*kr\.", text)
    if not price_m:
        return None
    price = int(price_m.group(1).replace(".", ""))

    # Size: "{number} m2" (Home uses m2 not m²)
    size_m = re.search(r"(\d+(?:[,.]\d+)?)\s*m2\b", text)
    size = float(size_m.group(1).replace(",", ".")) if size_m else 0.0

    # Address: first line with a 4-digit zip
    address = ""
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        if re.search(r"\b\d{4}\b", line) and "kr" not in line.lower() and "m2" not in line.lower():
            address = line
            break

    # Listing ID: extract "sag-XXXXXXXX" from href
    sag_m = re.search(r"sag-(\d+)", href or "")
    listing_id = sag_m.group(1) if sag_m else ""

    if not listing_id or not price or not size:
        return None

    return {
        "id": listing_id,
        "source": "home",
        "url": f"https://home.dk{href}" if href.startswith("/") else href,
        "title": address,
        "price": price,
        "size": size,
        "rooms": 0,  # Not available on listing cards
        "neighborhood": neighborhood,
        "address": address,
    }


async def _scrape_page(page, url: str, consent_dismissed: list) -> list[dict]:
    """Load one page and extract matching listings."""
    await page.goto(url, wait_until="networkidle", timeout=40000)
    await page.wait_for_timeout(3000)

    if not consent_dismissed:
        await dismiss_consent(page)
        await page.wait_for_timeout(2000)
        consent_dismissed.append(True)

    cards = await page.query_selector_all(CARD_SELECTOR)
    listings = []
    for card in cards:
        try:
            text = await card.inner_text()
            link_el = await card.query_selector("a[href*='/salg/']")
            href = await link_el.get_attribute("href") if link_el else ""
            parsed = _parse_card(text, href)
            if parsed:
                listings.append(parsed)
        except Exception:
            continue
    return listings


async def scrape_with_browser(browser) -> list[dict]:
    """Scrape Home.dk Capital Region listings and return target-zip apartments."""
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.set_extra_http_headers(HEADERS)
    consent_dismissed: list = []
    all_listings: list[dict] = []
    seen_ids: set[str] = set()

    try:
        results = await _scrape_page(page, SEARCH_URL, consent_dismissed)
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_listings.append(r)
        print(f"  [home] page 1: {len(results)} cards, {len(all_listings)} in target area")

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
            print(f"  [home] page {page_num}: {len(paged)} cards, {added} new in target area")
            if added == 0:
                break
    except Exception as e:
        print(f"  [home] error: {e}")
    finally:
        await page.close()

    return all_listings


def scrape_home() -> list[dict]:
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
    listings = scrape_home()
    print(json.dumps(listings[:3], indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(listings)}")
