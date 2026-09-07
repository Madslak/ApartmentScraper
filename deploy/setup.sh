#!/usr/bin/env bash
# One-time (idempotent) provisioning for the Apartment Scout pipeline on a
# fresh Hetzner VPS (Ubuntu 22.04/24.04). Re-runnable: safe to run again to
# update the checkout, dependencies, and cron.
#
# Usage (as a sudo-capable user on the VPS):
#   REPO_URL=git@github.com:<you>/ApartmentScraper.git deploy/setup.sh
# or, if you already cloned the repo and run this from inside it:
#   deploy/setup.sh
#
# What it does:
#   1. Installs system prerequisites (git, curl, ca-certificates).
#   2. Sets the system timezone to Europe/Copenhagen.
#   3. Installs uv (Python + dependency manager) if missing.
#   4. Clones/updates the repo into APP_DIR.
#   5. `uv sync` + installs the Playwright Chromium browser with its system deps.
#   6. Initialises the SQLite database.
#   7. Installs the cron jobs (pipeline + bot) and a logrotate policy.
#
# It does NOT create the server or write your secrets — create `.env` yourself
# (see deploy/.env.example and docs/hetzner-setup.md).
set -euo pipefail

# --- Config (override via environment) --------------------------------------
TZ_NAME="${TZ_NAME:-Europe/Copenhagen}"
BRANCH="${BRANCH:-main}"
REPO_URL="${REPO_URL:-}"

# Resolve APP_DIR: if this script lives inside a checkout, use that checkout;
# otherwise default to ~/ApartmentScraper and clone into it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    APP_DIR="${APP_DIR:-$HOME/ApartmentScraper}"
fi

echo "==> APP_DIR = $APP_DIR"
echo "==> TZ      = $TZ_NAME"
echo "==> BRANCH  = $BRANCH"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

# --- 1. System prerequisites ------------------------------------------------
echo "==> Installing system prerequisites..."
$SUDO apt-get update -y
$SUDO apt-get install -y git curl ca-certificates

# --- 2. Timezone ------------------------------------------------------------
echo "==> Setting timezone to $TZ_NAME..."
$SUDO timedatectl set-timezone "$TZ_NAME" || echo "  (timedatectl unavailable; skipping)"

# --- 3. uv ------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || { echo "uv not on PATH after install"; exit 1; }
echo "==> uv: $(uv --version)"

# --- 4. Clone / update the repo ---------------------------------------------
if [ ! -d "$APP_DIR/.git" ]; then
    if [ -z "$REPO_URL" ]; then
        echo "ERROR: $APP_DIR is not a git checkout and REPO_URL is unset."
        echo "       Set REPO_URL=... or clone the repo into $APP_DIR first."
        exit 1
    fi
    echo "==> Cloning $REPO_URL -> $APP_DIR..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
    echo "==> Updating existing checkout in $APP_DIR..."
    git -C "$APP_DIR" fetch --all --prune
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" pull --ff-only
fi
cd "$APP_DIR"

# --- 5. Python deps + Playwright browser ------------------------------------
echo "==> Syncing Python dependencies (uv manages the Python version)..."
uv sync

echo "==> Installing Playwright Chromium + system libraries..."
$SUDO env "PATH=$PATH" uv run playwright install --with-deps chromium

# --- 6. Database ------------------------------------------------------------
echo "==> Initialising the database..."
uv run python -c "import sys; sys.path.insert(0, 'src'); from database import init_db; init_db()"

# --- 7. Cron + logrotate ----------------------------------------------------
echo "==> Installing cron jobs..."
# Install only the marked block (not the human-facing header comments), so a
# re-run strips-and-reinstalls cleanly instead of accumulating comment lines.
CRON_RENDERED="$(sed "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/crontab" | awk '
    /^# >>> APARTMENT-SCOUT >>>/ {f=1}
    f {print}
    /^# <<< APARTMENT-SCOUT <<</ {f=0}
')"
# Replace only our managed block (between the APARTMENT-SCOUT markers); leave any
# other crontab lines untouched. awk drops the old block if present.
EXISTING="$(crontab -l 2>/dev/null | awk '
    /^# >>> APARTMENT-SCOUT >>>/ {skip=1}
    skip==0 {print}
    /^# <<< APARTMENT-SCOUT <<</ {skip=0}
' || true)"
printf '%s\n%s\n' "$EXISTING" "$CRON_RENDERED" | crontab -
echo "  Installed crontab:"
crontab -l | sed 's/^/    /'

echo "==> Installing logrotate policy..."
sed "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/logrotate.apartmentscraper" \
    | $SUDO tee /etc/logrotate.d/apartmentscraper >/dev/null

# --- Done -------------------------------------------------------------------
echo
echo "==> Setup complete."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "!!  No .env found. Copy deploy/.env.example to $APP_DIR/.env and fill it in:"
    echo "      cp $APP_DIR/deploy/.env.example $APP_DIR/.env && nano $APP_DIR/.env"
fi
echo "    Test the pipeline now:   $APP_DIR/deploy/run-pipeline.sh"
echo "    Cron will run it daily at 09:00 $TZ_NAME."
