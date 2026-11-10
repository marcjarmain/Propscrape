# PropScrape — weekly property market monitor

## Windows setup

1. In GitHub Desktop select **Propscrape**, then **Fetch origin → Pull origin**.
2. Click **Show in Explorer** and double-click **setup_weekly.bat** once.
3. Double-click **run.bat** (or **open_dashboard.bat**) to start the local dashboard server if needed and open it. Neither command starts a scrape.

## Always-on dashboard server

Right-click **setup_server.bat → Run as administrator** once to install **Propscrape Dashboard** in Windows Task Scheduler. It starts at PC startup, before login, has no execution time limit, and is configured to restart after failure. This administrator step is needed for a boot task running as SYSTEM. Keep this repository in a trusted local folder; the task executes its server.py with that account. It cannot run while the PC is off or asleep. Reinstall if you move the folder or Python installation.

Open **http://127.0.0.1:8768** or double-click **run.bat**. The server binds to this PC only. It reads the database without changing it, updates the dashboard every 30 seconds, shows recent runs, partial/failed attempts, stale data, missing backups, suburb counts and stored listings. Filters include houses and R6m–R8m. Logs and report downloads are available. Opening, refreshing or starting this server never requests Property24 pages. Weekly collection remains a separate task; the page does not claim to verify the Windows task schedule.

To remove the boot task, run **remove_server.bat** as administrator. A server previously started manually stops at reboot. If the dashboard does not open, check data/logs/server.log or whether another application uses port 8768. Data remains intact.

Python 3 must already work. Setup imports your existing output/listings.csv if present, preserving observation dates and correcting numeric prices using original price text. The old CSV is a baseline with unverified coverage, not a complete market snapshot. Setup does not start a scrape.

The Windows task **Propscrape Weekly** runs **Monday 09:00 in your PC's local time**. Keep the PC clock on South Africa time for 09:00 SAST. The PC must be on, online and you must be signed in. Windows is configured to catch up when available. The schedule is NOT active until setup succeeds on your PC. If Windows denies registration, inspect the error. Reinstall the task if you move the repository.

Use **remove_weekly.bat** to remove the collection schedule; data is retained. **scrape_now.bat** explicitly starts a manual collection. **run.bat** and **open_dashboard.bat** open the dashboard without contacting Property24.

## Useful outputs

- Per-suburb, property-type and price-band listing counts and median asking prices.
- Individual asking-price changes between complete snapshots.
- First and last observed dates, observation count and days between first and last observation.
- Advertised under-offer or sold/unavailable wording, when present in search-card text.
- Listings missing since the previous complete snapshot, NOT assumed sold.
- Historical weekly tables for inventory and median asking prices.

The default covers the **Southern Suburbs regional search**, not all Cape Town. Counts are listing IDs, not unique houses or confirmed available stock. Multiple agents may list the same home. Advertised statuses are text matches needing verification; absent labels mean unknown. Days observed are a lower bound on history, not actual days on market; relisting under a new ID starts a new history. Missing listings may be withdrawn, relisted, outside the search or sold.

The live dashboard is at http://127.0.0.1:8768. The older offline report remains at output/dashboard.html. No extra Python packages are needed. output/market.json is suitable for an LLM. CSV reports: suburb_summary.csv, listings_history.csv, price_changes.csv, missing_listings.csv and weekly_trends.csv. Downloads reflect the last generated report, which may be older than the database if report generation failed.

Price bands: below R4m; R4m to below R6m; R6m–R8m; above R8m–R10m; above R10m; unknown. Median changes can reflect a changing mix of properties, not changes in the value of an individual home. These are asking prices, not achieved sales.

## Data and collection quality

History is saved in data/market.sqlite3. Every attempt is retained, including failed/partial runs. The dashboard uses the latest complete snapshot and separately shows the latest attempt. Partial runs do not create inventory or price-change trends. Before any complete run exists, the baseline is displayed with a partial-data warning. Large inventory declines are flagged for coverage review. A completed pagination pass does not prove every listing was supplied or that results stayed static during collection.

Each distinct search URL has its own history. Search-card sizes remain unspecified when erf versus floor area is not clear. Listing detail pages are not fetched.

Page HTML is cached in data/pages; logs are in data/logs. A one-generation database backup is made after collection. Back up the whole data folder independently. Old page caches can be deleted to reclaim space without deleting the database.

## Request behaviour

The collector uses **60 seconds between pages**, one at a time, up to 100 pages (about an hour for 58 pages). It stops on errors, restrictions, unrecognised cards and pagination loops. No automatic retries, proxy rotation or CAPTCHA bypass. A lock prevents overlapping runs; scheduled attempts are skipped when an attempt occurred within six days.

This reduces load; it is not a verified safe rate or permission to scrape. Property24's [terms](https://www.property24.com/terms-and-conditions) restrict automated copying; obtain permission where needed. Robots rules are checked before collection.

After a forced shutdown, confirm collection has stopped before deleting a stale data/run.lock. The repository is public; data/, output/ and database files are ignored by git. Keep local data private.

## Commands

```
py -3 market.py --report-only
py -3 market.py --import-csv output/listings.csv
py -3 market.py --max-pages 5 --delay 60
py -3 server.py --open
py -3 -m unittest -v test_market.py test_server.py
```

The five-page command is a real collection test and is treated as partial. The legacy propscrape.py exporter and editable subject.json remain available; use market.py or scrape_now.bat for persistent history. The history report does not make valuations against the subject.

Ten automated checks cover parser/history, empty/corrupt database handling, preservation of complete snapshots after failures, and read-only dashboard endpoints. Windows task installation and a fresh live collection still require verification on your PC. Automated Chromium visual testing was blocked by the development environment's process/socket restrictions.

