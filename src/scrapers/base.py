"""Shared constants and utilities for all scrapers."""

import re

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


async def dismiss_consent(page) -> None:
    """Click whichever cookie consent button is present, if any."""
    for text in ["Afvis og luk", "Accepter og luk", "Accepter alle", "Accepter", "Tillad alle"]:
        try:
            btn = page.get_by_text(text, exact=True)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


# Reverse mapping: zip → neighborhood name (built from NEIGHBORHOOD_ZIPS)
ZIP_TO_NEIGHBORHOOD: dict[int, str] = {
    z: nb
    for nb, zips in NEIGHBORHOOD_ZIPS.items()
    for z in zips
}

# Set of all target zip codes for fast membership check
TARGET_ZIPS: set[int] = set(ZIP_TO_NEIGHBORHOOD)


def neighborhood_for_zip(zip_code: int) -> str | None:
    """Return the neighborhood name for a zip code, or None if not a target zip."""
    return ZIP_TO_NEIGHBORHOOD.get(zip_code)


def canonical_key(listing: dict) -> str:
    """Normalize address to a cross-source dedup key: street+housenumber+zip.

    Used to detect the same physical apartment listed on multiple sites.
    Returns empty string if address is missing or unparseable.
    """
    addr = (listing.get("address") or "").lower()
    if not addr:
        return ""
    zip_match = re.search(r"\b(\d{4})\b", addr)
    zip_code = zip_match.group(1) if zip_match else ""
    # Street name: everything before the first digit or comma
    street = re.split(r"[\d,]", addr)[0].strip().replace(" ", "")
    # House number: first short number in the address
    nums = re.findall(r"\b(\d{1,3})\b", addr)
    house = nums[0] if nums else ""
    key = f"{street}{house}{zip_code}"
    return key if len(key) >= 5 else ""  # too short = not reliable
