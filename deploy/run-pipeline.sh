#!/usr/bin/env bash
# Cron wrapper for the daily scrape -> score -> notify pipeline.
#
# Replaces the macOS launchd job (launchd/com.apartmentscraper.plist) on the
# Hetzner VPS. Self-locating: resolves the project root relative to this file,
# so it works regardless of the deploy path or the invoking user.
#
# Cron installs it via deploy/setup.sh. Run manually to test:
#   deploy/run-pipeline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

# cron runs with a minimal PATH; uv installs to ~/.local/bin by default.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# No `caffeinate` needed (that was macOS-only, to keep the laptop awake).
# The VPS is always on and networked; pipeline.wait_for_network() returns
# immediately.
exec uv run src/pipeline.py
