# Roadmap

## ✅ Phase 2 — Multi-source scraping (complete)

- ✅ Refactored `src/scraper.py` into `src/scrapers/` package
- ✅ Nybolig.dk scraper (Capital Region, paginated, ~100 Copenhagen listings)
- ✅ Home.dk scraper (Capital Region, paginated, ~56 Copenhagen listings)
- ✅ Cross-source address deduplication (realtor sites overwrite Boligsiden duplicates)
- ✅ DB migration: composite `(id, source)` primary key
- ✅ Source badge + filter in Streamlit UI

### Research findings: EDC, Danbolig, and Boligsiden coverage

**Why Nybolig + Home are worth scraping:**
Boligsiden aggregates ~99% of public listings, but Nybolig and Home add value via:
1. **Timing lag** — new listings appear on agent sites hours before syncing to Boligsiden
2. **Filter differences** — our Boligsiden search caps at 5.5M DKK / 50m² min; agent sites
   return listings just outside those bounds
3. In testing, Nybolig + Home found ~90 additional unique Copenhagen listings not in
   the Boligsiden results

**EDC and Danbolig — not worth direct scraping:**
- EDC.dk: blocked by CHEQ (IP-tier, fires before JS runs — JS patches don't help)
- Danbolig.dk: blocked by Cloudflare WAF
- Both are already fully aggregated by Boligsiden — their listings appear there within hours
- Best path: use `api.boligsiden.dk/search/cases` (no auth, returns JSON) and filter by
  `realtor.name` to get EDC/Danbolig-sourced listings. Stubs are in place if this is ever built.

**The real gap — "skuffesalg" (off-market / drawer sales):**
Nybolig and others run private buyer registries that distribute pre-market listings directly to
registered buyers. These **never appear on any public portal** — not on Boligsiden, not on
Nybolig.dk itself. Not scrapeable. The Facebook group scraper (Phase 4) partially fills this gap.

**ScrapeGraphAI:** Not useful here — it is an LLM extraction layer that runs on top of standard
Playwright. It does not bypass bot detection; CHEQ and Cloudflare block the underlying browser
before any content is fetched.

## ✅ Phase 3 — Telegram interactions (complete)

- ✅ Inline buttons on each notification: **💾 Gem** / **❌ Afvis**
- ✅ Clicking **Gem** marks listing as saved in the database (`saved=1`)
- ✅ Clicking **Afvis** marks listing as dismissed (`dismissed=1`)
- ✅ `/saved` command lists all saved listings with links
- ✅ Saved listings tracked separately and never expire
- ✅ Claude (Sonnet) drafts a personalized Danish outreach on Save
  - Draft sent with **✉️ Brug udkast** / **⏭️ Spring over** inline buttons
  - "Brug udkast" sends the text in a code block for easy copy-paste
- New files: `src/bot.py` (polling bot), `src/contacter.py` (Claude draft)
- Run bot: `uv run src/bot.py` (separate persistent process from the pipeline)

## Phase 4 — Facebook group scraper

- Scrape Copenhagen apartment Facebook groups (e.g. "Andelsboliger til salg")
- Requires injecting login session cookies into Playwright
- Partially fills the "skuffesalg" gap — private deals that never reach any portal
- Add `src/scrapers/facebook.py` — fits the existing multi-source architecture

## Phase 5 — Reliability & hosting

- Migrate the scheduled pipeline from macOS launchd to a Hetzner VPS (~€5/month)
- Runs 24/7 independently of the laptop being on or awake
- Add a cron job on the VPS instead of launchd
