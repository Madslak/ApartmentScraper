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


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection to the project database."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create tables and seed default config if the database is new."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                price INTEGER,
                size REAL,
                rooms INTEGER,
                neighborhood TEXT,
                address TEXT,
                score REAL,
                is_soft_match INTEGER DEFAULT 0,
                notified INTEGER DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT
            )
        """)
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
    """Insert a new listing or update price/score if it already exists."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM listings WHERE id = ?", (listing["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE listings SET last_seen=?, price=?, score=?, is_soft_match=? WHERE id=?",
                (now, listing["price"], listing["score"], listing["is_soft_match"], listing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO listings
                   (id, url, title, price, size, rooms, neighborhood, address,
                    score, is_soft_match, notified, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                (
                    listing["id"], listing["url"], listing["title"],
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
            """SELECT id, url, title, price, size, rooms, neighborhood, address,
                      score, is_soft_match
               FROM listings WHERE notified=0 ORDER BY score DESC"""
        ).fetchall()
    keys = ["id", "url", "title", "price", "size", "rooms",
            "neighborhood", "address", "score", "is_soft_match"]
    return [dict(zip(keys, row)) for row in rows]


def mark_notified(listing_ids: list[str]) -> None:
    """Mark a batch of listings as notified so they are not re-sent tomorrow."""
    with get_connection() as conn:
        conn.executemany(
            "UPDATE listings SET notified=1 WHERE id=?",
            [(lid,) for lid in listing_ids],
        )
        conn.commit()


def get_all_listings() -> list[dict]:
    """Return all stored listings ordered by score descending."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, url, title, price, size, rooms, neighborhood, address,
                      score, is_soft_match, first_seen, last_seen
               FROM listings ORDER BY score DESC"""
        ).fetchall()
    keys = ["id", "url", "title", "price", "size", "rooms",
            "neighborhood", "address", "score", "is_soft_match", "first_seen", "last_seen"]
    return [dict(zip(keys, row)) for row in rows]
