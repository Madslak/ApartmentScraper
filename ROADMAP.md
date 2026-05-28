# Roadmap

## Phase 2 — Multi-source scraping

- Add scrapers for individual realtor sites (Nybolig, Home.dk, EDC, Danbolig)
- Add Facebook group scraper (requires injecting login session cookies into Playwright)
- Refactor `src/scraper.py` into `src/scrapers/` with one file per source:
  ```
  src/scrapers/
  ├── base.py          — shared Playwright fetch logic
  ├── boligsiden.py
  ├── nybolig.py
  ├── home.py
  └── facebook.py
  ```

## Phase 3 — Owner contacter

- Build a contacter that drafts a personalised message to the seller/agent
- Use Claude (Sonnet) to write the outreach based on listing details
- Human-in-the-loop: Telegram bot sends the draft and waits for approval before sending
- Reply "send" in Telegram to trigger the contact, "skip" to discard

## Phase 4 — Phone notifications (human in the loop)

- Ping on phone for high-score listings above a threshold
- Telegram inline buttons on each listing: "Contact owner" / "Save" / "Dismiss"
- Saved listings tracked separately in the database

## Phase 5 — Reliability & hosting

- Migrate the scheduled pipeline from macOS launchd to a Hetzner VPS (~€5/month)
- Runs 24/7 independently of the laptop being on or awake
- Add a cron job on the VPS instead of launchd
