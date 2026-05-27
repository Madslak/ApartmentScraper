# Commands

## Setup (first time only)

```bash
# Install dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium

# Initialise database
uv run python -c "import sys; sys.path.insert(0, 'src'); from database import init_db; init_db()"

# Load the daily launchd job (runs pipeline at 09:00)
cp launchd/com.apartmentscraper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.apartmentscraper.plist
```

---

## Daily use

```bash
# Start the Streamlit UI
uv run streamlit run src/app.py

# Run the scraper pipeline manually (scrape + score + notify)
uv run src/pipeline.py

# Test Telegram notification with a dummy listing
uv run src/notifier.py
```

---

## Config

```bash
# Reset database config to defaults (overwrites any UI changes)
uv run python -c "import sys; sys.path.insert(0, 'src'); from database import DEFAULT_CONFIG, save_config; save_config(DEFAULT_CONFIG)"
```

---

## launchd (scheduled job)

```bash
# Check the job is registered (shows "- 0 com.apartmentscraper" when healthy)
launchctl list | grep apartmentscraper

# Reload after editing the plist
launchctl unload ~/Library/LaunchAgents/com.apartmentscraper.plist
cp launchd/com.apartmentscraper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.apartmentscraper.plist

# Check logs from the last scheduled run
cat scraper.log
cat scraper.error.log
```

---

## Database

```bash
# Open the SQLite database directly
sqlite3 apartments.db

# Useful queries inside sqlite3
SELECT COUNT(*) FROM listings;
SELECT title, price, score, neighborhood FROM listings ORDER BY score DESC LIMIT 10;
SELECT title, price, price_previous FROM listings WHERE is_price_drop=1;
.quit
```

---

## Git

```bash
# Commit and push changes
git add -A && git commit -m "your message" && git push
```
