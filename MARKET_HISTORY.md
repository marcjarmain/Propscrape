# PropScrape market-history extension

This feature retains **all** imported listing snapshots in a local SQLite database at `data/market.sqlite3`. Keep this database backed up; it is deliberately not committed to the public repository.

## Quick start (Windows)

1. Pull the branch (or merge the pull request), then double-click `weekly_collect.bat` for a baseline snapshot. Or import an earlier JSON: `py market.py import output/comparison.json`.
2. Double-click `dashboard.bat` and open http://127.0.0.1:8768 on that desktop.
3. Run `install_weekly_task.bat` to schedule a Sunday 08:00 collection using Windows Task Scheduler. The desktop must be on and connected. You can edit the task schedule in Windows Task Scheduler.
4. Repeat regularly; price history begins with the earliest snapshot available. The dashboard reads the local database and does not require cloud hosting.

**Coverage:** The collector currently queries one Property24 Southern Suburbs search URL, **not all of Cape Town**. Weekly means an attempted collection; completeness depends on pagination and permitted access. The database records failures and incomplete coverage. Do not evade robots rules, IP restrictions, rate limits or challenges. Seek permission or use an authorised data feed for reliable full-market weekly coverage.

**Status:** The historical schema supports explicit `listing_status` and `status_evidence` fields (`for_sale`, `under_offer`, `sold`) if these are supplied by an authorised source. Existing search-card collection usually cannot verify sale status. Never assume disappeared = sold; property may be withdrawn, relisted, or inaccessible.

**Counting:** Price brackets count observed advertisements in the latest run (not unique houses if duplicate IDs/listings or different agents), not concluded transactions. An incomplete crawl is not a true total-market count.

## Next development priorities

- Add authorised suburb searches with per-search crawl completeness, regional history, and deduplication across URLs.
- Capture explicit source status badge text when present, with validation against live layouts.
- Build genuine market trend comparisons between complete like-for-like snapshots, including new listings, reductions and inventory over time.
- Match deeds / verified sale-price data (licensed feed) for sold-price estimation.
- Optional secure cloud sync for mobile dashboard access; do not expose unauthenticated local dashboard to the internet.

## Commands

```powershell
py market.py collect --max-pages 100
py market.py import output/comparison.json
py market.py dashboard --port 8768
```
