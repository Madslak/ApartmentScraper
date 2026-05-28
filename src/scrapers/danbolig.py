"""Danbolig.dk scraper — currently blocked by Cloudflare/WAF.

Danbolig blocks headless Playwright requests with a WAF challenge page.
This stub returns an empty list until a bypass strategy is implemented.
"""

import asyncio


async def scrape_with_browser(browser) -> list[dict]:
    """Danbolig scraper placeholder — site blocks headless browsers."""
    print("  [danbolig] skipped — site blocks headless browsers (WAF/Cloudflare)")
    return []


def scrape_danbolig() -> list[dict]:
    """Standalone entry point."""
    return asyncio.run(scrape_with_browser(None))
