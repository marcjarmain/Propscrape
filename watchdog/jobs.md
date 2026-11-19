# Scrape watchdog: what counts as a problem

The watchdog (a scheduled Claude task) reads this file each run. Edit
thresholds here, no code change needed. State lives in state.json.

Alert rule: email mdjarmain@gmail.com ONLY when a job is unhealthy, once per
problem. Do not email again for the same problem unless it clears and returns,
or 7 days pass. Healthy runs write to state.json and stay silent.

## propscrape (weekly, runs on Marc's PC, Monday 09:00 SAST)
- Source: status/heartbeat.json in this repo (pushed by the PC after each run)
- Late: latest_run.started older than 10 days (7 plus 3 days grace for a PC
  that was off; Windows catches up)
- Failed: latest_run.complete is 0, or last_job.exit_code is not 0
- Thin: latest_run.count below 70 percent of the median of the previous
  complete runs
- Silent: heartbeat.json missing or "written" older than 10 days
- Grace: if heartbeat.json does not exist yet, stay silent until 2026-11-30,
  then alert once (the PC needs a pull and one run after the update)

## airscraper (Airscraper connector)
- Source: list_runs, get_collection_state, get_coverage
- Late: no successful run in the last 48 hours, unless collection is
  deliberately paused (then stay silent)
- Failed: latest run failed, or errors in collection state
- Thin: coverage or listings stored clearly below the recent norm

## portinspector (Portinspector connector)
- Source: get_run_status
- Late: no completed pipeline run in the last 48 hours
- Failed: latest run errored or is stuck running for more than 6 hours

## Reporting
- One line per job in state.json: status, checked time, reason.
- Never trade, never touch any other data. Read-only checks plus the email.
