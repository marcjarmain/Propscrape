"""Write a small health record for the watchdog and push it to GitHub.
Contains no listings, only run health. Never raises: a failure here must
not affect the scrape, so problems are appended to data/logs/heartbeat.log."""
import datetime, json, pathlib, sqlite3, subprocess, traceback
root = pathlib.Path(__file__).resolve().parent
out = root / "status" / "heartbeat.json"
log = root / "data" / "logs" / "heartbeat.log"

def build():
    db = sqlite3.connect(f"file:{root/'data'/'market.sqlite3'}?mode=ro", uri=True)
    cols = "id,started,finished,complete,reason,count"
    rows = db.execute(f"SELECT {cols} FROM runs ORDER BY id DESC LIMIT 8").fetchall()
    db.close()
    runs = [dict(zip(cols.split(","), r)) for r in rows]
    job = {}
    try: job = json.loads((root / "data" / "last_job.json").read_text(encoding="utf-8"))
    except Exception: pass
    return {
        "job": "propscrape",
        "written": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "expected_every_days": 7,
        "last_job": job,
        "latest_run": runs[0] if runs else None,
        "recent_runs": runs,
    }

def git(*a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=120)

def main():
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    git("pull", "--rebase", "--autostash", "-q")
    git("add", "status/heartbeat.json")
    if git("diff", "--cached", "--quiet").returncode:
        git("commit", "-q", "-m", "Heartbeat")
        r = git("push", "-q")
        if r.returncode: raise RuntimeError("push failed: " + r.stderr[:300])

if __name__ == "__main__":
    try: main()
    except Exception:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().isoformat() + "\n" + traceback.format_exc() + "\n")
