"""Instagram broker scraper via the Graph API Business Discovery edge.

Unlike the rest of this package, this is NOT a Playwright browser scrape — it is
an HTTP call to the Facebook-Login Graph API. It reads recent posts from brokers'
public Business/Creator accounts via the `business_discovery` edge, which requires
our own linked IG Business account and a Facebook-Login token (`EAA…`, starts with
EAA — an Instagram-Login `IGAA…` token does NOT support business_discovery).

Setup and gotchas: docs/instagram-setup.md.
"""

import os

import httpx
from dotenv import load_dotenv

from .base import NEIGHBORHOOD_ZIPS

load_dotenv()

GRAPH = "https://graph.facebook.com/v21.0"

# Our own apartmentwatcher IG Business account (Page "Apartment Watch").
# Stable and not a secret; override via env if the account ever changes.
IG_USER_ID = os.environ.get("INSTAGRAM_IG_USER_ID", "17841424332024827")

# Copenhagen apartment brokers whose IG accounts resolve via Business Discovery.
# Verified 2026-06-08; danbolig/edc/estate.dk do NOT resolve (not business accts).
BROKERS = ["nybolig", "home.dk", "ivaneltoftnielsen"]

# Graph error subcode meaning "username not found" (typo / not a business account).
_USERNAME_NOT_FOUND = 2207013

# Caption terms that flag a Copenhagen-area post (neighborhoods + city aliases).
_CPH_TERMS = [n.lower() for n in NEIGHBORHOOD_ZIPS] + ["københav", "kbh", "frederiksberg"]


def fetch_broker_media(token: str, username: str, limit: int = 10) -> list[dict]:
    """Return recent posts for one broker via business_discovery.

    Each post dict: {id, caption, permalink, timestamp, media_type}.
    Returns [] if the username can't be found, so one bad handle never aborts a run.
    """
    fields = (
        f"business_discovery.username({username})"
        f"{{media.limit({limit}){{id,caption,permalink,timestamp,media_type}}}}"
    )
    r = httpx.get(
        f"{GRAPH}/{IG_USER_ID}",
        params={"fields": fields, "access_token": token},
        timeout=30,
    )
    data = r.json()
    if "error" in data:
        if data["error"].get("error_subcode") == _USERNAME_NOT_FOUND:
            return []
        raise RuntimeError(
            f"business_discovery({username}) failed: {data['error'].get('message')}"
        )
    return data["business_discovery"]["media"]["data"]


def is_copenhagen(caption: str | None) -> bool:
    """True if a caption mentions a Copenhagen-area neighborhood or the city.

    Brokers like nybolig/home.dk post nationwide, so this trims the noise down to
    the capital area. ivaneltoftnielsen is Copenhagen-focused (most posts pass).
    """
    if not caption:
        return False
    c = caption.lower()
    return any(term in c for term in _CPH_TERMS)


def scrape(brokers: list[str] | None = None, limit: int = 10) -> list[dict]:
    """Fetch recent broker posts and return the Copenhagen-relevant ones.

    Each listing: {source, broker, id, caption, url, timestamp, media_type}.
    The `id` is the IG media id — use it to dedup against already-seen posts.
    """
    token = os.environ["INSTAGRAM_TOKEN"]
    listings: list[dict] = []
    for username in brokers or BROKERS:
        for post in fetch_broker_media(token, username, limit):
            if is_copenhagen(post.get("caption")):
                listings.append(
                    {
                        "source": "instagram",
                        "broker": username,
                        "id": post["id"],
                        "caption": post.get("caption", ""),
                        "url": post.get("permalink"),
                        "timestamp": post.get("timestamp"),
                        "media_type": post.get("media_type"),
                    }
                )
    return listings


def _seen_ids() -> set[str]:
    """Load already-seen media IDs from the DB (lazy import to avoid coupling).

    The import path differs between running as ``python -m src.scrapers.instagram``
    (``src`` package) and being imported by the pipeline (``src`` on ``sys.path``),
    so try the package-relative form first and fall back to the flat one.
    """
    try:
        from ..database import get_seen_instagram_ids
    except ImportError:
        from database import get_seen_instagram_ids
    return get_seen_instagram_ids()


def new_posts(brokers: list[str] | None = None, limit: int = 10) -> list[dict]:
    """Return only the Copenhagen posts not seen on a prior run.

    Scrapes via ``scrape()`` then drops any post whose IG media ``id`` is already
    in the seen-ID store, so repeat runs surface each post exactly once. This does
    NOT mark the returned posts as seen — the caller records them via
    ``database.mark_instagram_seen()`` only after they've been handled, so a
    downstream failure never silently loses a post (mirrors the notified flag).
    """
    seen = _seen_ids()
    return [post for post in scrape(brokers, limit) if post["id"] not in seen]


if __name__ == "__main__":
    # POC: print only NEW Copenhagen-relevant broker posts, then mark them seen
    # so a re-run demonstrates the dedup (it will show 0 until brokers post again).
    try:
        from ..database import mark_instagram_seen
    except ImportError:
        from database import mark_instagram_seen

    results = new_posts()
    print(f"Found {len(results)} NEW Copenhagen-relevant broker posts:\n")
    for r in results:
        cap = r["caption"].replace("\n", " ")[:90]
        print(f"[{r['timestamp'][:10]}] @{r['broker']}  {r['media_type']}")
        print(f"  {cap}")
        print(f"  {r['url']}\n")

    mark_instagram_seen(results)
    print(f"Marked {len(results)} post(s) as seen — re-running shows only newer posts.")
