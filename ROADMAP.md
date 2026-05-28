# Roadmap

## ✅ Phase 2 — Multi-source scraping (complete)

- ✅ Refactored `src/scraper.py` into `src/scrapers/` package
- ✅ Nybolig.dk scraper (Capital Region, paginated, ~100 Copenhagen listings)
- ✅ Home.dk scraper (Capital Region, paginated, ~56 Copenhagen listings)
- ✅ Cross-source address deduplication (realtor sites overwrite Boligsiden duplicates)
- ✅ DB migration: composite `(id, source)` primary key
- ✅ Source badge + filter in Streamlit UI
- ⏸ EDC.dk — blocked by CHEQ anti-bot (stub in place, revisit later)
- ⏸ Danbolig.dk — blocked by Cloudflare WAF (stub in place, revisit later)

## Phase 3 — Telegram interactions (human in the loop)

- Inline buttons on each Telegram listing notification: **Save** / **Dismiss**
- Clicking **Save** marks the listing as saved in the database
- `/saved` command in Telegram shows all saved listings (with links)
- Saved listings are tracked separately and never expire from the saved list
- Build a contacter that drafts a personalised message to the seller/agent
  - Use Claude (Sonnet) to write the outreach based on listing details
  - Reply "send" in Telegram to trigger the contact, "skip" to discard

## Phase 4 — Facebook group scraper

- Scrape Copenhagen apartment Facebook groups (e.g. "Andelsboliger til salg")
- Requires injecting login session cookies into Playwright
- Add `src/scrapers/facebook.py` — fits the existing multi-source architecture

## Phase 5 — Reliability & hosting

- Migrate the scheduled pipeline from macOS launchd to a Hetzner VPS (~€5/month)
- Runs 24/7 independently of the laptop being on or awake
- Add a cron job on the VPS instead of launchd
