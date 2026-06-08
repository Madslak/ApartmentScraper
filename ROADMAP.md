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

## Phase 4 — Instagram broker scraper

**Goal:** Watch Copenhagen apartment brokers' Instagram accounts for new posts about
apartments and surface them through the existing notification pipeline. Start with a POC
proving feasibility; defer any messaging function (see note below).

**Chosen approach: official Instagram Graph API — Business Discovery** (not third-party scraping).

The Business Discovery endpoint reads another Business/Creator account's media by username:

```
GET /<MY_IG_USER_ID>
  ?fields=business_discovery.username(<broker_username>){
            media{caption,permalink,timestamp,media_type,media_url}
          }
```

Returns **caption, permalink, timestamp, media_url** per post — enough to detect new posts,
text-match for Copenhagen apartments, and dedup by post ID / timestamp.

**Setup requirements (one-time):**
- Our own Instagram **Business or Creator** account, linked to a Facebook Page
- A Meta Developer App
- Permissions: `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`
- **App Review (Advanced Access)** to query accounts other than our own dev account
- Target broker accounts must be Business/Creator accounts (they almost certainly are)

**POC success criteria:**
1. Authenticate and obtain a long-lived access token
2. Pull recent media for 2–3 known Copenhagen broker accounts via Business Discovery
3. Filter posts by caption keywords / neighborhood (reuse `base.py` zip/neighborhood logic)
4. Confirm we can detect *new* posts since last run (track seen post IDs)

**Architecture fit:** Add `src/scrapers/instagram.py`. Note this is an **HTTP API call, not a
Playwright browser scrape** — it won't use the shared browser instance in
`scrapers/__init__.py`, so wire it in as a separate (non-browser) source rather than into
`_scrape_all_async`'s browser task group.

**Constraints & limitations:**
- Free and ToS-compliant, but App Review adds setup overhead vs. a quick scrape
- Only works against Business/Creator targets
- Hashtag search (`/<hashtag_id>/recent_media`) is an alternative but weak: public posts only,
  24h window, max 30 hashtags / 7 days, and the `username` field is unavailable — so we can't
  attribute posts to brokers. Per-account Business Discovery is the better fit.

**Deferred — messaging function (do NOT build in this phase):**
The official Instagram Messaging API **cannot cold-DM brokers**. A message can only be sent
*after the broker messages us first*, within a 24-hour reply window. An automated outreach DM
is therefore impossible via the API. Open question for a later phase: mirror the Phase 3
Telegram pattern (Claude **drafts** a Danish DM for manual copy-paste) if outreach is wanted.

**Rejected alternative — third-party Apify scrapers:**
The gathered skills.sh links (`apidojo-io/instagram-scraper`, `serpdownloaders`, etc.) are all
**Apify actors**: no IG login needed, scrape public profiles directly, return posts/captions.
But they require a paid Apify plan (per-run cost), violate Instagram ToS, and break when IG
changes its frontend — unacceptable for a 24/7 pipeline. Useful only as a throwaway feasibility
check; the official API is the foundation we build on.

## Phase 5 — Facebook group scraper

- Scrape Copenhagen apartment Facebook groups (e.g. "Andelsboliger til salg")
- Requires injecting login session cookies into Playwright
- Partially fills the "skuffesalg" gap — private deals that never reach any portal
- Add `src/scrapers/facebook.py` — fits the existing multi-source architecture

## Phase 6 — Reliability & hosting

- Migrate the scheduled pipeline from macOS launchd to a Hetzner VPS (~€5/month)
- Runs 24/7 independently of the laptop being on or awake
- Add a cron job on the VPS instead of launchd
