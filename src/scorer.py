"""Scoring and filtering logic for apartment listings.

Each listing receives a score: (m² / price_in_millions) × neighborhood_multiplier.
Higher score = better value in a more preferred area.

Hard limits exclude listings entirely. Soft limits (hard=False + leniency > 0)
allow listings just outside the threshold — these are flagged as is_soft_match=True
and shown in yellow in the UI.
"""

from database import get_config

NEIGHBORHOOD_ALIASES: dict[str, str] = {
    "nørrebro": "Nørrebro",
    "frederiksberg": "Frederiksberg",
    "indre by": "Indre By",
    "københavn k": "Indre By",
    "kbh k": "Indre By",
    "vesterbro": "Vesterbro",
    "københavn v": "Vesterbro",
    "kbh v": "Vesterbro",
    "østerbro": "Østerbro",
    "københavn ø": "Østerbro",
    "amager": "Amager",
    "amager vest": "Amager",
    "amager øst": "Amager",
    "københavn s": "Amager",
    "københavn sv": "Amager",
    "valby": "Valby",
    "vanløse": "Other",
    "brønshøj": "Other",
    "bispebjerg": "Other",
    "nordvest": "Other",
}


def normalize_neighborhood(raw: str) -> str:
    """Map a raw neighborhood string from the scraper to a canonical name."""
    if not raw:
        return "Other"
    key = raw.strip().lower()
    for alias, canonical in NEIGHBORHOOD_ALIASES.items():
        if alias in key:
            return canonical
    return "Other"


def score_listing(listing: dict, config: dict) -> tuple[float, bool]:
    """Compute a listing's score and whether it is a soft-limit match.

    Score formula: (size_m2 / price_millions) * neighborhood_multiplier
    Returns (score, is_soft_match).
    """
    price = listing.get("price", 0) or 0
    size = listing.get("size", 0) or 0
    rooms = listing.get("rooms", 0) or 0
    neighborhood = normalize_neighborhood(listing.get("neighborhood", ""))

    if price <= 0 or size <= 0:
        return 0.0, False

    multipliers = config.get("neighborhood_multipliers", {})
    nb_multiplier = multipliers.get(neighborhood, multipliers.get("Other", 0.50))
    base_score = (size / (price / 1_000_000)) * nb_multiplier

    is_soft_match = False
    price_max = config["price_max"]
    price_ceiling = price_max * (1 + config["price_leniency"] / 100)
    if not config["price_hard"] and price > price_max and price <= price_ceiling:
        is_soft_match = True

    size_min = config["size_min"]
    size_floor = size_min * (1 - config["size_leniency"] / 100)
    if not config["size_hard"] and size < size_min and size >= size_floor:
        is_soft_match = True

    if not config["rooms_hard"] and rooms < config["rooms_min"]:
        is_soft_match = True

    return round(base_score, 4), is_soft_match


def passes_hard_filters(listing: dict, config: dict) -> bool:
    """Return False if the listing is outside every allowed threshold (including leniency)."""
    price = listing.get("price", 0) or 0
    size = listing.get("size", 0) or 0
    rooms = listing.get("rooms", 0) or 0

    price_max = config["price_max"]
    price_ceiling = price_max * (1 + config["price_leniency"] / 100) if not config["price_hard"] else price_max
    if price > price_ceiling:
        return False

    size_min = config["size_min"]
    size_floor = size_min * (1 - config["size_leniency"] / 100) if not config["size_hard"] else size_min
    if size < size_floor:
        return False

    if config["rooms_hard"] and rooms < config["rooms_min"]:
        return False

    return True


def score_and_filter(listings: list[dict]) -> list[dict]:
    """Filter listings against current config and return them sorted by score descending."""
    config = get_config()
    results = []
    for listing in listings:
        if not passes_hard_filters(listing, config):
            continue
        score, is_soft = score_listing(listing, config)
        listing["score"] = score
        listing["is_soft_match"] = int(is_soft)
        listing["neighborhood"] = normalize_neighborhood(listing.get("neighborhood", ""))
        results.append(listing)
    return sorted(results, key=lambda x: x["score"], reverse=True)
