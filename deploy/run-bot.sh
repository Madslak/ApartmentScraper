#!/usr/bin/env bash
# Cron wrapper for the interactive Telegram bot (Save/Dismiss buttons, /saved,
# Claude outreach drafts).
#
# Mirrors the macOS launchd job (launchd/com.apartmentscraper.bot.plist): the
# bot runs for a fixed window each day rather than persistently. BOT_RUN_MINUTES
# makes src/bot.py exit after that many minutes (see bot.main()).
#
# NOTE: a time-boxed bot only handles button taps inside its window. For 24/7
# button handling, run the bot as a persistent systemd service instead — see
# docs/hetzner-setup.md ("Optional: run the bot 24/7").
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export BOT_RUN_MINUTES="${BOT_RUN_MINUTES:-60}"

exec uv run src/bot.py
