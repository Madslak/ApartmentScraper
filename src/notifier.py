"""Telegram notification sender.

Formats scored listings into readable Telegram messages and sends them
to the configured chat. Capped at MAX_LISTINGS_PER_MESSAGE per run to
avoid spam on days with many new listings.

Run directly to send a test message: `uv run notifier.py`
"""

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

load_dotenv()

MAX_LISTINGS_PER_MESSAGE = 10


def format_listing(listing: dict, rank: int) -> str:
    """Format a single listing dict as a Telegram Markdown message."""
    soft = " _(leniency match)_" if listing.get("is_soft_match") else ""
    price_fmt = f"{listing['price']:,}".replace(",", ".")

    if listing.get("is_price_drop") and listing.get("price_previous"):
        old_fmt = f"{listing['price_previous']:,}".replace(",", ".")
        drop_pct = (listing["price_previous"] - listing["price"]) / listing["price_previous"] * 100
        price_line = f"Pris: {price_fmt} kr _(var {old_fmt} kr, -{drop_pct:.1f}%)_"
        header = f"*PRISFALD — {listing['title']}*{soft}"
    else:
        price_line = f"Pris: {price_fmt} kr"
        header = f"*#{rank} — {listing['title']}*{soft}"

    return (
        f"{header}\n"
        f"💰 {price_line}\n"
        f"📐 {listing['size']} m²  |  🛏 {listing['rooms']} rum\n"
        f"📍 {listing['neighborhood']}\n"
        f"⭐ Score: {listing['score']:.2f}\n"
        f"🔗 {listing['url']}"
    )


async def _send(token: str, chat_id: str, listings: list[dict]) -> None:
    """Send header + one message per listing to the Telegram chat."""
    bot = Bot(token=token)
    if not listings:
        await bot.send_message(
            chat_id=chat_id,
            text="*Apartment Scout* — ingen nye boliger i dag.",
            parse_mode="Markdown",
        )
        return

    count = len(listings)
    plural = "er" if count != 1 else ""
    header = f"*Apartment Scout* — {count} ny{plural} bolig{plural} fundet!"
    await bot.send_message(chat_id=chat_id, text=header, parse_mode="Markdown")

    for i, listing in enumerate(listings[:MAX_LISTINGS_PER_MESSAGE], start=1):
        lid = listing["id"]
        src = listing.get("source", "boligsiden")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💾 Gem", callback_data=f"save|{lid}|{src}"),
            InlineKeyboardButton("❌ Afvis", callback_data=f"dismiss|{lid}|{src}"),
        ]])
        await bot.send_message(
            chat_id=chat_id,
            text=format_listing(listing, i),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


def send_listings(listings: list[dict]) -> None:
    """Send new listings to Telegram. Reads credentials from environment."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    asyncio.run(_send(token, chat_id, listings))


if __name__ == "__main__":
    test = [{
        "title": "Testgade 1, 2. tv., 2200 København N",
        "price": 3200000,
        "size": 72.0,
        "rooms": 3,
        "neighborhood": "Nørrebro",
        "score": 22.5,
        "is_soft_match": 0,
        "url": "https://www.boligsiden.dk",
    }]
    send_listings(test)
    print("Test notification sent.")
