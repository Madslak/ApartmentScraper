"""SQLite persistence layer.

Handles the database schema, config storage, and listing upserts.
All other modules import from here — nothing else touches the DB directly.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "apartments.db"

DEFAULT_CONFIG = {
    "price_max": 4000000,
    "price_leniency": 15,
    "price_hard": False,
    "size_min": 50,
    "size_leniency": 10,
    "size_hard": False,
    "rooms_min": 2,
    "rooms_hard": True,
    "room_multipliers": {
        "1": 0.80,
        "2": 0.90,
        "3+": 1.00,
    },
    "neighborhood_multipliers": {
        "Nørrebro": 1.00,
        "Frederiksberg": 0.92,
        "Indre By": 0.85,
        "Vesterbro": 0.80,
        "Østerbro": 0.75,
        "Amager": 0.65,
        "Valby": 0.58,
        "Other": 0.50,
    },
}

PRICE_DROP_THRESHOLD = 0.02  # re-notify when price falls by more than this fraction

_NEW_LISTINGS_SCHEMA = """
    CREATE TABLE listings (
        id TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'boligsiden',
        url TEXT,
        title TEXT,
        price INTEGER,
        size REAL,
        rooms INTEGER,
        neighborhood TEXT,
        address TEXT,
        score REAL,
        is_soft_match INTEGER DEFAULT 0,
        is_price_drop INTEGER DEFAULT 0,
        price_previous INTEGER,
        notified INTEGER DEFAULT 0,
        first_seen TEXT,
        last_seen TEXT,
        PRIMARY KEY (id, source)
    )
"""


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection to the project database."""
    return sqlite3.connect(DB_PATH)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply schema migrations for databases created before multi-source support."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}

    # Pre-existing single-column migrations
    for col, definition in [
        ("is_price_drop", "INTEGER DEFAULT 0"),
        ("price_previous", "INTEGER"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {definition}")

    # Multi-source migration: add source column then rebuild table with composite PK
    if "source" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN source TEXT NOT NULL DEFAULT 'boligsiden'")
        conn.execute("DROP TABLE IF EXISTS _listings_old")
        conn.execute("ALTER TABLE listings RENAME TO _listings_old")
        conn.execute(_NEW_LISTINGS_SCHEMA)
        conn.execute("""
            INSERT INTO listings
                (id, source, url, title, price, size, rooms, neighborhood, address,
                 score, is_soft_match, is_price_drop, price_previous,
                 notified, first_seen, last_seen)
            SELECT
                id, source, url, title, price, size, rooms, neighborhood, address,
                score, is_soft_match, is_price_drop, price_previous,
                notified, first_seen, last_seen
            FROM _listings_old
        """)
        conn.execute("DROP TABLE _listings_old")

    conn.commit()


def init_db() -> None:
    """Create tables and seed default config if the database is new."""
    with get_connection() as conn:
        conn.execute(_NEW_LISTINGS_SCHEMA.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
        _migrate(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        for key, value in DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        conn.commit()


def get_config() -> dict:
    """Return the full config dict from the database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def save_config(config: dict) -> None:
    """Persist a config dict to the database, overwriting existing keys."""
    with get_connection() as conn:
        for key, value in config.items():
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        conn.commit()


def upsert_listing(listing: dict) -> None:
    """Insert a new listing or update it if it already exists.

    If the price has dropped by more than PRICE_DROP_THRESHOLD since last seen,
    the listing is re-queued for notification with is_price_drop=1.
    """
    now = datetime.now().isoformat()
    lid = listing["id"]
    source = listing.get("source", "boligsiden")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT price FROM listings WHERE id=? AND source=?", (lid, source)
        ).fetchone()
        if row:
            old_price = row[0]
            new_price = listing["price"]
            drop = (old_price - new_price) / old_price if old_price else 0
            is_price_drop = drop > PRICE_DROP_THRESHOLD
            conn.execute(
                """UPDATE listings
                   SET last_seen=?, price=?, score=?, is_soft_match=?,
                       is_price_drop=?,
                       price_previous=CASE WHEN ? THEN ? ELSE price_previous END,
                       notified=CASE WHEN ? THEN 0 ELSE notified END
                   WHERE id=? AND source=?""",
                (
                    now, new_price, listing["score"], listing["is_soft_match"],
                    int(is_price_drop),
                    is_price_drop, old_price,
                    is_price_drop,
                    lid, source,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO listings
                   (id, source, url, title, price, size, rooms, neighborhood, address,
                    score, is_soft_match, is_price_drop, price_previous,
                    notified, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0,NULL,0,?,?)""",
                (
                    lid, source, listing["url"], listing["title"],
                    listing["price"], listing["size"], listing["rooms"],
                    listing["neighborhood"], listing["address"],
                    listing["score"], listing["is_soft_match"],
                    now, now,
                ),
            )
        conn.commit()


def get_unsent_listings() -> list[dict]:
    """Return all listings not yet sent via Telegram, best score first."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, source, url, title, price, size, rooms, neighborhood, address,
                      score, is_soft_match, is_price_drop, price_previous
               FROM listings WHERE notified=0 ORDER BY score DESC"""
        ).fetchall()
    keys = ["id", "source", "url", "title", "price", "size", "rooms",
            "neighborhood", "address", "score", "is_soft_match",
            "is_price_drop", "price_previous"]
    return [dict(zip(keys, row)) for row in rows]


def mark_notified(pairs: list[tuple[str, str]]) -> None:
    """Mark a batch of listings as notified so they are not re-sent tomorrow.

    Each element of pairs is (id, source).
    """
    with get_connection() as conn:
        conn.executemany(
            "UPDATE listings SET notified=1 WHERE id=? AND source=?",
            pairs,
        )
        conn.commit()


def get_all_listings() -> list[dict]:
    """Return all stored listings ordered by score descending."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, source, url, title, price, size, rooms, neighborhood, address,
                      score, is_soft_match, first_seen, last_seen
               FROM listings ORDER BY score DESC"""
        ).fetchall()
    keys = ["id", "source", "url", "title", "price", "size", "rooms",
            "neighborhood", "address", "score", "is_soft_match", "first_seen", "last_seen"]
    return [dict(zip(keys, row)) for row in rows]
