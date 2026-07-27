# Instagram broker scraper — setup

How `src/scrapers/instagram.py` reads brokers' posts, and how to reproduce the setup.

## How it works

Reads recent posts from brokers' public **Business/Creator** accounts via the
**Business Discovery** edge of the Facebook-Login Graph API:

```
GET https://graph.facebook.com/v21.0/<OUR_IG_USER_ID>
    ?fields=business_discovery.username(<broker>){media{caption,permalink,timestamp,media_type}}
    &access_token=<EAA_TOKEN>
```

It returns full post history (not just 24h — that limit is only on the *hashtag*
endpoint), so new posts are detected by tracking already-seen media IDs.

## Accounts / IDs

- Our IG Business account: **apartmentwatcher**, IG User ID **17841424332024827**
- Linked Facebook Page: **Apartment Watch** (id 1053379241202916)
- `IG_USER_ID` is hardcoded in `instagram.py` (stable, not secret); override with
  env `INSTAGRAM_IG_USER_ID` if the account changes.

## Token

`.env` → `INSTAGRAM_TOKEN` must be a **Facebook-Login token (`EAA…`)**.

⚠️ An Instagram-Login token (`IGAA…`, from `graph.instagram.com`) does **not**
support `business_discovery` ("nonexisting field" error). Wrong token type is the
single most likely cause of failure.

Generate via **Graph API Explorer** (developers.facebook.com/tools/explorer):
1. Select the app → **Get User Access Token**
2. Permissions: `instagram_basic`, `instagram_manage_insights`,
   `pages_read_engagement`, `pages_show_list`
3. On the consent popup, **select the "Apartment Watch" Page and the
   apartmentwatcher IG account** (easy to skip — without it the token sees nothing)
4. Confirm the token starts with `EAA`

Short-lived tokens last ~1–2h (fine for the POC). Production needs a long-lived
token + App Review — see below.

## Gotchas (learned the hard way)

- **`/me/accounts` returns empty** `{"data":[]}` because "Apartment Watch" is a
  New Pages Experience page. Harmless — query the page directly
  (`/<page_id>?fields=instagram_business_account`) or use the hardcoded IG User ID.
- **Dev-mode tester invite:** while the app is in Development mode, any IG account
  it touches needs an **Instagram Tester** invite (App roles → Roles), accepted
  inside Instagram at `instagram.com/accounts/manage_access/` → *Tester invites*.
- **error_subcode 2207013** = broker username not found (not a permission error).
  Treated as empty in code.
- Targets must be Business/Creator accounts. Verified working: `nybolig`,
  `home.dk`, `ivaneltoftnielsen`. Not found: `danbolig`, `edc`, `estate.dk`.

## Run the POC

```bash
uv run python -m src.scrapers.instagram
```

Prints Copenhagen-relevant broker posts (caption + permalink), filtered by
neighborhood/city keywords from `scrapers/base.py`.

## Still TODO for production

- **App Review (Advanced Access)** for the permissions, so we can query brokers
  unattended beyond dev-mode tester accounts.
- **Long-lived token** via the `fb_exchange_token` exchange (60-day), refreshed.
- Curate the broker list; wire results into the notifier/pipeline.