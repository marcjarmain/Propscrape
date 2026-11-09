#!/usr/bin/env python3
"""Historical SQLite storage, weekly collection and local dashboard for PropScrape."""
import argparse
import csv
import datetime as dt
import html
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "market.sqlite3"
BRACKETS = [(0, 2000000, "< R2m"), (2000000, 4000000, "R2–4m"),
            (4000000, 6000000, "R4–6m"), (6000000, 8000000, "R6–8m"),
            (8000000, 10000000, "R8–10m"), (10000000, 15000000, "R10–15m"),
            (15000000, None, "R15m+")]

def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(path)
    cx.row_factory = sqlite3.Row
    cx.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS runs(
      id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, search_url TEXT,
      pages INTEGER NOT NULL, listing_count INTEGER NOT NULL,
      complete INTEGER NOT NULL, stop_reason TEXT, imported_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS listings(
      listing_id TEXT PRIMARY KEY, url TEXT, first_seen TEXT, last_seen TEXT);
    CREATE TABLE IF NOT EXISTS observations(
      run_id INTEGER NOT NULL REFERENCES runs(id),
      listing_id TEXT NOT NULL REFERENCES listings(listing_id),
      observed_at TEXT NOT NULL, asking_price_zar REAL, suburb TEXT,
      region TEXT, property_type TEXT, bedrooms REAL, bathrooms REAL,
      advertised_size_m2 REAL, listing_status TEXT NOT NULL,
      status_evidence TEXT, title TEXT, PRIMARY KEY(run_id, listing_id));
    CREATE INDEX IF NOT EXISTS idx_obs_listing ON observations(listing_id,run_id);
    CREATE INDEX IF NOT EXISTS idx_obs_price ON observations(asking_price_zar);
    CREATE TABLE IF NOT EXISTS events(
      run_id INTEGER NOT NULL, listing_id TEXT NOT NULL,
      event_type TEXT NOT NULL, old_value TEXT, new_value TEXT,
      PRIMARY KEY(run_id,listing_id,event_type));
    """)
    return cx

def parse_status(row):
    # Only explicit labels qualify; 'sold' must not be inferred from disappearance.
    label = str(row.get("listing_status") or "").lower().strip()
    evidence = str(row.get("status_evidence") or "")
    if label in ("sold", "under_offer", "for_sale"):
        return label, evidence
    evidence = str(row.get("status_text") or row.get("badge_text") or "")
    t = evidence.lower()
    if "sold" in t: return "sold", evidence
    if "under offer" in t or "sale pending" in t: return "under_offer", evidence
    return "for_sale", evidence

def import_snapshot(path, db=DB):
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    coverage = source.get("coverage") or {}
    rows = source.get("listings") or []
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    stamps = [r.get("observed_at") for r in rows if r.get("observed_at")]
    stamp = min(stamps) if stamps else now
    complete = bool(coverage.get("complete"))
    with connect(db) as cx:
        cur = cx.execute("""INSERT INTO runs(observed_at,search_url,pages,listing_count,complete,stop_reason,imported_at)
          VALUES(?,?,?,?,?,?,?)""", (stamp, rows[0].get("search_url") if rows else None,
          len(coverage.get("pages") or []), len(rows), int(complete),
          coverage.get("stop_reason","unknown"),now))
        rid = cur.lastrowid
        previous = {}
        previous_run = cx.execute("SELECT id,search_url FROM runs WHERE id < ? ORDER BY id DESC LIMIT 1",(rid,)).fetchone()
        # Compare only like-for-like regional searches.
        if previous_run and previous_run["search_url"] == (rows[0].get("search_url") if rows else None):
            previous = {r["listing_id"]:r for r in cx.execute(
                "SELECT * FROM observations WHERE run_id=?", (previous_run["id"],))}
        present = set()
        for row in rows:
            lid = str(row.get("listing_id") or "").strip()
            if not lid or lid in present: continue
            present.add(lid)
            status,evidence = parse_status(row)
            cx.execute("""INSERT INTO listings(listing_id,url,first_seen,last_seen) VALUES(?,?,?,?)
              ON CONFLICT(listing_id) DO UPDATE SET last_seen=excluded.last_seen,url=excluded.url""",
              (lid,row.get("url"),stamp,stamp))
            values = (rid,lid,row.get("observed_at") or stamp,row.get("asking_price_zar"),
                      row.get("suburb"),row.get("region"),row.get("property_type"),
                      row.get("bedrooms"),row.get("bathrooms"),row.get("advertised_size_m2"),
                      status,evidence,row.get("title"))
            cx.execute("""INSERT INTO observations(run_id,listing_id,observed_at,asking_price_zar,suburb,
              region,property_type,bedrooms,bathrooms,advertised_size_m2,listing_status,status_evidence,title)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",values)
            old=previous.get(lid)
            if old:
                p0,p1=old["asking_price_zar"],row.get("asking_price_zar")
                if p0 is not None and p1 is not None and float(p0)!=float(p1):
                    cx.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)",
                               (rid,lid,"price_change",str(p0),str(p1)))
                if old["listing_status"]!=status:
                    cx.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)",
                               (rid,lid,"status_change",old["listing_status"],status))
            else:
                cx.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)",
                           (rid,lid,"first_observed",None,status))
        # Absence is meaningful only after a complete, same-search crawl.
        if complete and previous:
            for lid in previous.keys()-present:
                cx.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)",
                           (rid,lid,"not_seen_in_complete_run",None,None))
    return rid

def report(db=DB):
    with connect(db) as cx:
        runs=[dict(r) for r in cx.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 52")]
        if not runs: return {"runs":[],"totals":{},"brackets":[],"changes":[]}
        latest=runs[0]
        obs=[dict(r) for r in cx.execute(
            "SELECT * FROM observations WHERE run_id=?",(latest["id"],))]
        changes=[dict(r) for r in cx.execute("""
            SELECT e.*, o.suburb,o.title,l.url FROM events e
            LEFT JOIN observations o ON o.run_id=e.run_id AND o.listing_id=e.listing_id
            LEFT JOIN listings l ON l.listing_id=e.listing_id
            WHERE e.run_id=? ORDER BY e.event_type,e.listing_id""",(latest["id"],))]
        brackets=[]
        for low,high,name in BRACKETS:
            group=[r for r in obs if r["asking_price_zar"] is not None
                   and r["asking_price_zar"]>=low
                   and (high is None or r["asking_price_zar"]<high)]
            brackets.append({"name":name,"count":len(group),
                "under_offer":sum(r["listing_status"]=="under_offer" for r in group),
                "sold_label":sum(r["listing_status"]=="sold" for r in group)})
        return {"runs":runs,"latest":latest,
            "totals":{"listed":len(obs),"under_offer":sum(r["listing_status"]=="under_offer" for r in obs),
                      "sold_label":sum(r["listing_status"]=="sold" for r in obs),
                      "price_changes":sum(r["event_type"]=="price_change" for r in changes),
                      "not_seen":sum(r["event_type"]=="not_seen_in_complete_run" for r in changes)},
            "brackets":brackets,"changes":changes[:500]}

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>PropScrape Market History</title>
<style>body{font:15px system-ui;background:#f5f7fb;color:#14243a;margin:0;padding:24px}
main{max-width:1150px;margin:auto}h1{margin-bottom:4px}.muted{color:#617186}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
.card,section{background:white;border:1px solid #e1e6ef;border-radius:12px;padding:18px}
.card strong{font-size:27px;display:block;margin-top:8px}section{margin:16px 0;overflow:auto}
table{border-collapse:collapse;width:100%;min-width:650px}th,td{padding:10px;text-align:left;border-bottom:1px solid #e8edf3}
th{color:#53647b}a{color:#1858a2}.bar{height:15px;background:#4c79bc;border-radius:4px}
small{color:#62738b}select{padding:7px}</style>
<main><h1>PropScrape · Market history</h1><p class="muted" id="subtitle"></p>
<div class="cards" id="cards"></div><section><h2>Asking-price brackets</h2>
<p class="muted">Current crawl only. Counts are not the whole market unless coverage is complete.</p>
<table><thead><tr><th>Bracket</th><th>Listings</th><th>Share of observed inventory</th><th>Under offer</th><th>Explicitly sold</th></tr></thead>
<tbody id="brackets"></tbody></table></section>
<section><h2>Recent collection history</h2><table><thead><tr><th>Date</th><th>Observed</th><th>Pages</th><th>Coverage</th></tr></thead><tbody id="runs"></tbody></table></section>
<section><h2>Latest listing changes</h2><p class="muted">Disappearance is not a confirmed sale; incomplete crawls never generate disappearance events.</p>
<table><thead><tr><th>Listing</th><th>Event</th><th>Previous</th><th>Current</th></tr></thead><tbody id="events"></tbody></table></section>
<p class="muted">Source: public listing advertisements. Prices are asking prices, not transaction prices. Status labels require explicit source evidence.</p>
</main><script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>v==null?'—':'R'+Number(v).toLocaleString('en-ZA',{maximumFractionDigits:0});
fetch('/api/report').then(r=>r.json()).then(d=>{
let last=d.latest;if(!last){document.querySelector('#subtitle').textContent='No snapshots imported yet';return}
document.querySelector('#subtitle').textContent='Latest snapshot: '+new Date(last.observed_at).toLocaleString()+' · '+(last.complete?'Complete pagination':'Incomplete: '+last.stop_reason);
let t=d.totals;document.querySelector('#cards').innerHTML=[['Observed listings',t.listed],['Under offer',t.under_offer],['Sold labels',t.sold_label],['Price changes',t.price_changes],['Unverified disappearances',t.not_seen]].map(x=>'<div class="card">'+esc(x[0])+'<strong>'+x[1]+'</strong></div>').join('');
let mx=Math.max(1,...d.brackets.map(x=>x.count));
document.querySelector('#brackets').innerHTML=d.brackets.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+x.count+'</td><td><div class="bar" style="width:'+Math.round(100*x.count/mx)+'%"></div></td><td>'+x.under_offer+'</td><td>'+x.sold_label+'</td></tr>').join('');
document.querySelector('#runs').innerHTML=d.runs.map(x=>'<tr><td>'+esc(x.observed_at.slice(0,10))+'</td><td>'+x.listing_count+'</td><td>'+x.pages+'</td><td>'+esc(x.complete?'Complete':x.stop_reason)+'</td></tr>').join('');
document.querySelector('#events').innerHTML=d.changes.map(x=>'<tr><td>'+(x.url?'<a target="_blank" rel="noopener" href="'+esc(x.url)+'">'+esc(x.title||x.listing_id)+'</a>':esc(x.listing_id))+'<small> '+esc(x.suburb||'')+'</small></td><td>'+esc(x.event_type)+'</td><td>'+esc(x.event_type==='price_change'?money(x.old_value):x.old_value)+'</td><td>'+esc(x.event_type==='price_change'?money(x.new_value):x.new_value)+'</td></tr>').join('');
}).catch(e=>document.querySelector('#subtitle').textContent='Unable to read database: '+e);
</script></html>"""

def serve(db,port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urlparse(self.path).path
            if path=="/api/report":
                body=json.dumps(report(db),ensure_ascii=False).encode()
                kind="application/json"
            elif path=="/":
                body=PAGE.encode()
                kind="text/html; charset=utf-8"
            else:
                self.send_error(404);return
            self.send_response(200)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"Dashboard: http://127.0.0.1:{port}",flush=True)
    server.serve_forever()

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    imp=sub.add_parser("import");imp.add_argument("file",type=Path)
    collect=sub.add_parser("collect");collect.add_argument("--url");collect.add_argument("--max-pages",type=int,default=100)
    dash=sub.add_parser("dashboard");dash.add_argument("--port",type=int,default=8768)
    args=p.parse_args()
    if args.action=="import": print("Imported run",import_snapshot(args.file))
    elif args.action=="dashboard": serve(DB,args.port)
    else:
        folder=ROOT/"output"
        cmd=[sys.executable,str(ROOT/"propscrape.py"),"--output",str(folder),"--max-pages",str(args.max_pages)]
        if args.url:cmd+=["--url",args.url]
        snap=folder/"comparison.json"
        before=snap.stat().st_mtime_ns if snap.exists() else None
        rc=subprocess.run(cmd,cwd=ROOT,check=False).returncode
        if snap.exists() and (before is None or snap.stat().st_mtime_ns!=before):
            print("Imported run",import_snapshot(snap))
        else:
            print("No new snapshot written; database unchanged",file=sys.stderr)
        sys.exit(rc)
if __name__=="__main__": main()
