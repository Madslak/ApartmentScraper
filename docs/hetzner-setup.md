# Hetzner VPS setup (cron)

Runbook for migrating the Apartment Scout pipeline off the macOS laptop
(launchd) onto a small always-on Hetzner VPS driven by **cron**. This replaces
`launchd/com.apartmentscraper.plist` and `launchd/com.apartmentscraper.bot.plist`
(kept in the repo for the legacy macOS path).

**Why:** launchd only fires while the laptop is awake and online. A ~€4–5/month
Hetzner Cloud server runs the daily 09:00 scrape 24/7, independent of the laptop.

Everything below the "Create the server" step is automated by
[`deploy/setup.sh`](../deploy/setup.sh). The parts a human must do (they need an
account, payment, and secrets) are called out explicitly.

---

## 0. What you provide (human-only steps)

- A Hetzner Cloud account and a project (payment method on file).
- An SSH public key uploaded to Hetzner (for server login).
- Read access to this Git repo from the server: either a **deploy key**
  (recommended) or an HTTPS token. Alternatively, skip Git and `rsync` the code
  up (see step 3, option B).
- The secrets for `.env` (Telegram token + chat id, Anthropic key, optional
  Instagram token). See [`deploy/.env.example`](../deploy/.env.example).

## 1. Create the server

Hetzner Cloud Console → **Add Server**:

- **Location:** Nuremberg/Falkenstein/Helsinki — any EU is fine.
- **Image:** Ubuntu 24.04.
- **Type:** CX22 (shared vCPU, 2 vCPU / 4 GB) is comfortable for a headless
  Chromium scrape. The cheapest CX/CAX tier also works but give Chromium ≥2 GB
  RAM.
- **SSH key:** select the key you uploaded.
- Create, then note the server IP.

```bash
ssh root@<SERVER_IP>
# optional: create a non-root sudo user and use it for the rest
adduser deploy && usermod -aG sudo deploy && su - deploy
```

## 2. Get the code onto the server

Option A — clone via Git (recommended):

```bash
# with a deploy key configured, or an HTTPS token in the URL
git clone https://github.com/<you>/ApartmentScraper.git ~/ApartmentScraper
```

Option B — `rsync` from the laptop (no server-side Git access needed):

```bash
# run on the laptop, from the project root
rsync -av --exclude .git --exclude .venv --exclude '*.db' --exclude '*.log' \
  ./ deploy@<SERVER_IP>:~/ApartmentScraper/
```

## 3. Run the setup script

```bash
cd ~/ApartmentScraper
deploy/setup.sh
# or, if you did NOT clone yet, let the script clone for you:
# REPO_URL=https://github.com/<you>/ApartmentScraper.git deploy/setup.sh
```

The script is **idempotent** (safe to re-run to update). It:

1. installs `git`, `curl`, `ca-certificates`;
2. sets the system timezone to `Europe/Copenhagen`;
3. installs [`uv`](https://docs.astral.sh/uv/) if missing;
4. clones/updates the repo (only when needed);
5. runs `uv sync` and `uv run playwright install --with-deps chromium`
   (this apt-installs the browser's system libraries — needs sudo);
6. initialises the SQLite DB;
7. installs the cron jobs and a logrotate policy.

## 4. Add secrets

```bash
cp ~/ApartmentScraper/deploy/.env.example ~/ApartmentScraper/.env
nano ~/ApartmentScraper/.env   # fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, anthropicAPI, ...
chmod 600 ~/ApartmentScraper/.env
```

`.env` is gitignored — it lives only on the server, never in the repo.

## 5. Verify

```bash
# One manual pipeline run end-to-end (should scrape, score, and send Telegram):
~/ApartmentScraper/deploy/run-pipeline.sh

# Confirm the cron jobs are installed:
crontab -l

# Confirm the timezone (cron fires at 09:00 local):
timedatectl | grep 'Time zone'

# Watch the next scheduled run's output:
tail -f ~/ApartmentScraper/scraper.log ~/ApartmentScraper/scraper.error.log
```

Success = you receive the Telegram notification and `scraper.log` ends with
`=== Pipeline complete ... ===`.

---

## Schedule & timezone notes

- The daily scrape runs at **09:00 Copenhagen time**. `deploy/setup.sh` sets the
  system timezone, and `deploy/crontab` also pins `CRON_TZ=Europe/Copenhagen`,
  so the schedule is correct across CET/CEST without editing.
- The pipeline uses `datetime.now().astimezone()`, so log/notification
  timestamps follow the system timezone — set above.
- `caffeinate` (macOS keep-awake) and the launchd "wait for network" quirk are
  not needed on the VPS; `pipeline.wait_for_network()` just returns immediately.

## The bot: cron window vs. 24/7 service

By default the cron job runs the Telegram bot for **60 minutes from 09:00**
(mirrors the old launchd bot job via `BOT_RUN_MINUTES=60`). Save/Dismiss buttons
and `/saved` only respond during that window.

To make the bot respond **24/7**, run it as a systemd service instead and remove
the bot line from cron:

```ini
# /etc/systemd/system/apartment-bot.service
[Unit]
Description=Apartment Scout Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/home/deploy/ApartmentScraper
Environment=BOT_RUN_MINUTES=0
ExecStart=/home/deploy/.local/bin/uv run src/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now apartment-bot
# then remove the bot line from `crontab -e`
```

## Updating the deployment

```bash
cd ~/ApartmentScraper && deploy/setup.sh   # pulls latest, re-syncs deps, refreshes cron
# if running the bot as a service: sudo systemctl restart apartment-bot
```

## Troubleshooting

- **`uv: command not found` in cron** — the wrappers add `~/.local/bin` to
  `PATH`; confirm `uv` installed there (`ls ~/.local/bin/uv`).
- **Chromium fails to launch** — re-run
  `uv run playwright install --with-deps chromium`; ensure ≥2 GB RAM.
- **No Telegram message** — check `scraper.error.log`; verify `.env` values and
  that the bot has been started once (`/start`) so `TELEGRAM_CHAT_ID` is valid.
- **Wrong run time** — check `timedatectl`; the schedule is Copenhagen time.
- **Logs growing** — handled by `/etc/logrotate.d/apartmentscraper` (weekly, 8
  rotations, compressed).
