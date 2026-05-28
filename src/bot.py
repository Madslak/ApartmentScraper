"""Interactive Telegram bot for Apartment Scout.

Handles Save/Dismiss inline buttons on listing notifications, the /saved command,
and the Claude-powered outreach draft flow.

Run as a persistent process (separate from the daily pipeline):
    uv run src/bot.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from contacter import draft_outreach
from database import (
    dismiss_listing,
    get_listing,
    get_outreach_draft,
    get_saved_listings,
    init_db,
    save_listing,
    set_outreach_draft,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*🏠 Apartment Scout Bot*\n\n"
        "Kommandoer:\n"
        "• /saved — vis gemte boliger\n\n"
        "Brug knapperne under hver bolignotifikation til at gemme eller afvise en bolig.\n"
        "Når du gemmer, udformer jeg automatisk et udkast til henvendelse til mægleren.",
        parse_mode="Markdown",
    )


async def cmd_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    listings = get_saved_listings()
    if not listings:
        await update.message.reply_text("Du har ingen gemte boliger endnu.")
        return

    lines = ["*💾 Dine gemte boliger:*\n"]
    for i, lst in enumerate(listings, 1):
        price_fmt = f"{int(lst['price']):,}".replace(",", ".")
        lines.append(
            f"{i}. [{lst['title']}]({lst['url']}) — {price_fmt} kr, {lst['size']} m², {lst['rooms']} rum, {lst['neighborhood']}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split("|")
    action, listing_id, source = parts[0], parts[1], parts[2]

    if action == "save":
        save_listing(listing_id, source)
        await query.answer("✅ Gemt!")

        listing = get_listing(listing_id, source)
        if not listing:
            await query.message.reply_text("Boligen kunne ikke findes i databasen.")
            return

        status_msg = await query.message.reply_text("⏳ Udformer udkast til henvendelse...")

        try:
            draft = await asyncio.to_thread(draft_outreach, listing)
        except Exception as exc:
            log.error("draft_outreach failed: %s", exc)
            await status_msg.edit_text("❌ Kunne ikke udforme udkast. Prøv igen senere.")
            return

        set_outreach_draft(listing_id, source, draft)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✉️ Brug udkast", callback_data=f"use_draft|{listing_id}|{source}"),
            InlineKeyboardButton("⏭️ Spring over", callback_data=f"skip_draft|{listing_id}|{source}"),
        ]])
        await status_msg.edit_text(
            f"*Udkast til henvendelse:*\n\n{draft}",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    elif action == "dismiss":
        dismiss_listing(listing_id, source)
        await query.answer("❌ Afvist")
        await query.edit_message_reply_markup(reply_markup=None)

    elif action == "use_draft":
        draft = get_outreach_draft(listing_id, source)
        if not draft:
            await query.answer("Intet udkast fundet.")
            return
        await query.answer("📋 Tekst sendt!")
        await query.message.reply_text(
            f"```\n{draft}\n```",
            parse_mode="Markdown",
        )

    elif action == "skip_draft":
        await query.answer("⏭️ Udkast kasseret")
        await query.edit_message_reply_markup(reply_markup=None)


async def _run_timed(app: Application, seconds: int) -> None:
    """Run the bot for a fixed number of seconds, then shut down cleanly."""
    assert app.updater is not None
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("Bot polling for %d minutes", seconds // 60)
        await asyncio.sleep(seconds)
        await app.updater.stop()
        await app.stop()
    log.info("Bot shut down after %d minutes", seconds // 60)


def main() -> None:
    init_db()
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("saved", cmd_saved))
    app.add_handler(CallbackQueryHandler(handle_callback))

    run_minutes = int(os.environ.get("BOT_RUN_MINUTES", "0"))
    if run_minutes > 0:
        asyncio.run(_run_timed(app, run_minutes * 60))
    else:
        log.info("Bot polling started (indefinite)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
