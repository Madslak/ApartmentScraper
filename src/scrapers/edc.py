"""EDC.dk scraper — currently blocked by CHEQ anti-bot protection.

EDC actively blocks headless Playwright requests (HTTP 403 / CHEQ block).
This stub returns an empty list until a bypass strategy is implemented
(e.g., residential proxies, playwright-stealth, or cookie injection).
"""

import asyncio


async def scrape_with_browser(browser) -> list[dict]:
    """EDC scraper placeholder — site blocks headless browsers."""
    print("  [edc] skipped — site blocks headless browsers (CHEQ protection)")
    return []


def scrape_edc() -> list[dict]:
    """Standalone entry point."""
    return asyncio.run(scrape_with_browser(None))
