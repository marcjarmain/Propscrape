"""Local weekly listing history. Python standard library only."""
import argparse, csv, datetime as dt, html, json, os, re, sqlite3, statistics, sys
from pathlib import Path
from types import SimpleNamespace
import propscrape

ROOT = Path(__file__).resolve().parent
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started TEXT, finished TEXT,
      scope TEXT, complete INTEGER, reason TEXT, count INTEGER);
    CREATE TABLE IF NOT EXISTS observations(run_id INTEGER, listing_id TEXT, price REAL,
      status TEXT, data TEXT, PRIMARY KEY(run_id,listing_id));
    CREATE INDEX IF NOT EXISTS listing_history ON observations(listing_id,run_id);
    ''')
    return db

def normalise(row):
    r=dict(row)
    r['asking_price_zar']=propscrape.asking_price(r.get('price_text',''))
    if not r.get('property_type'):
        m=re.search(r'\b(townhouse|house|apartment|flat|vacant land|farm|commercial)\b',r.get('title','')+' '+r.get('price_text',''),re.I)
        r['property_type']=m.group(1).lower() if m else 'unknown'
    if r['property_type']=='flat': r['property_type']='apartment'
    text=(r.get('status_text','')+' '+r.get('description','')).lower()
    # These are observed marketing labels, not verified deeds transfers.
    r['advertised_status']='unknown'
    if re.search(r'\b(sold out|sold|no longer available)\b',text) and not re.search(r'\b(not sold|sold separately|sold furnished|sold unfurnished)\b',text):
        r['advertised_status']='advertised sold/unavailable'
    elif re.search(r'\b(under offer|offer pending|sale pending)\b',text):
        r['advertised_status']='advertised under offer'
    for key in ('bedrooms','bathrooms','parking','advertised_size_m2','erf_m2','floor_m2'):
        try: r[key]=float(r[key]) if r.get(key) not in ('',None) else None
        except (ValueError,TypeError): r[key]=None
    return r

def save_run(db, rows, coverage, scope, started=None):
    records={str(x['listing_id']):normalise(x) for x in rows if x.get('listing_id')}
    with db:
        cur=db.execute('INSERT INTO runs(started,finished,scope,complete,reason,count) VALUES(?,?,?,?,?,?)',
          (started or now(),now(),scope,int(coverage.get('complete',False)),coverage.get('stop_reason','unknown'),len(records)))
        rid=cur.lastrowid
        db.executemany('INSERT INTO observations VALUES(?,?,?,?,?)',[(rid,k,v['asking_price_zar'],v['advertised_status'],json.dumps(v,ensure_ascii=False)) for k,v in records.items()])
    return rid

def bracket(p):
    if p is None: return 'Price unknown'
    if p<4000000: return 'Below R4m'
    if p<6000000: return 'R4m to <R6m'
    if p<=8000000: return 'R6m–R8m'
    if p<=10000000: return '>R8m–R10m'
    return 'Above R10m'

def report(db, output, scope):
    output.mkdir(parents=True,exist_ok=True)
    runs=[dict(r) for r in db.execute('SELECT * FROM runs WHERE scope=? ORDER BY id',(scope,))]
    full=[r for r in runs if r['complete']]
    current=full[-1] if full else (runs[-1] if runs else None)
    previous=full[-2] if len(full)>1 else None
    def snapshot(r):
        return {o['listing_id']:json.loads(o['data']) for o in db.execute('SELECT * FROM observations WHERE run_id=?',(r['id'],))} if r else {}
    cur=snapshot(current); prev=snapshot(previous)
    history={}
    for o in db.execute('SELECT o.*,r.started FROM observations o JOIN runs r ON o.run_id=r.id WHERE r.scope=? ORDER BY r.id',(scope,)):
        history.setdefault(o['listing_id'],[]).append(dict(o))
    details=[]; changes=[]
    for lid,r in cur.items():
        h=history[lid]; first=h[0]['started']; last=h[-1]['started']
        days=(dt.datetime.fromisoformat(last)-dt.datetime.fromisoformat(first)).days
        old=prev.get(lid,{}).get('asking_price_zar'); price=r.get('asking_price_zar')
        change=price-old if old is not None and price is not None else None
        line={**r,'first_observed':first,'last_observed':last,'observed_span_days':max(0,days),
          'observations':len(h),'price_band':bracket(price),'previous_complete_price':old,'price_change_zar':change,
          'price_change_pct':round(change/old*100,2) if change is not None and old else None,
          'new_since_previous_complete':lid not in prev if previous else None}
        details.append(line)
        if change: changes.append({'listing_id':lid,'suburb':r.get('suburb'),'old_price':old,'new_price':price,'change_zar':change,'url':r.get('url')})
    missing=[{'listing_id':k,'suburb':v.get('suburb'),'price':v.get('asking_price_zar'),'url':v.get('url'),'status':'not observed in latest complete search — not evidence of sale'} for k,v in prev.items() if k not in cur]
    groups={}
    for r in details: groups.setdefault((r.get('suburb') or 'Unknown',r.get('property_type') or 'unknown',r['price_band']),[]).append(r)
    summaries=[]
    for (suburb,typ,band),items in sorted(groups.items()):
        ps=[r['asking_price_zar'] for r in items if r['asking_price_zar'] is not None]
        summaries.append({'suburb':suburb,'type':typ,'price_band':band,'observed_listings':len(items),
          'median_asking_price':statistics.median(ps) if ps else None,
          'advertised_under_offer':sum(r['advertised_status']=='advertised under offer' for r in items),
          'advertised_sold_unavailable':sum(r['advertised_status']=='advertised sold/unavailable' for r in items),
          'median_observed_days':statistics.median([r['observed_span_days'] for r in items])})
    # Historical subgroup series, using complete snapshots only; missing groups count as zero.
    trends=[]; trend_groups=set(); buckets=[]
    for run in full:
        counts={}
        for r in snapshot(run).values():
            key=(r.get('suburb') or 'Unknown',r.get('property_type') or 'unknown',bracket(r['asking_price_zar']))
            counts.setdefault(key,[]).append(r['asking_price_zar']); trend_groups.add(key)
        buckets.append((run,counts))
    for run,counts in buckets:
        for key in sorted(trend_groups):
            prices=counts.get(key,[]); known=[p for p in prices if p is not None]
            trends.append({'date':run['started'],'suburb':key[0],'type':key[1],'price_band':key[2],
              'observed_listings':len(prices),'median_asking_price':statistics.median(known) if known else None})
    payload={'scope':scope,'latest_attempt':runs[-1] if runs else None,'displayed_snapshot':current,
       'previous_complete':previous,'suburb_summary':summaries,'listings':details,'price_changes':changes,'missing':missing,'trend':trends,'runs':runs}
    (output/'market.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    def csvfile(name,records):
        with (output/name).open('w',newline='',encoding='utf-8-sig') as f:
            if not records: f.write('No records\n'); return
            keys=list(records[0]); writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader()
            for row in records:
                writer.writerow({k: ("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items() if k in keys})
    for name,records in [('listings_history.csv',details),('suburb_summary.csv',summaries),('price_changes.csv',changes),('missing_listings.csv',missing),('weekly_trends.csv',trends)]: csvfile(name,records)
    def table(records,keys):
        return '<table><thead><tr>'+''.join('<th>'+html.escape(k.replace('_',' ').title())+'</th>' for k in keys)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(k) if r.get(k) is not None else '—'))+'</td>' for k in keys)+'</tr>' for r in records)+'</tbody></table>'
    latest=runs[-1] if runs else {}
    warning='Latest attempt: '+str(latest.get('started','none'))+' — '+str(latest.get('reason','no data'))
    body='<h1>Southern Suburbs market monitor</h1><p>'+html.escape(warning)+'</p>'
    body+='<p>Displayed snapshot: '+html.escape(str(current['started'] if current else 'none'))+' | '+str(len(details))+' observed listings | '+str(len(changes))+' price changes | '+str(len(missing))+' missing since previous complete run</p>'
    body+='<p>Counts are listing IDs, not unique homes or confirmed available stock. Under-offer/sold labels are text matches to check. Days are since first observation, not true days on market. Disappearance does not prove a sale. Median changes can reflect a different mix of properties.</p>'
    if not full: body+='<p class="warning">No complete snapshot yet. The view is partial; no market movements inferred.</p>'
    if current and previous and len(cur)<.7*len(prev): body+='<p class="warning">Large inventory drop: verify coverage before interpreting missing listings.</p>'
    body+='<input id="filter" placeholder="Filter tables: suburb, house, price band…" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))">'
    body+='<h2>Listings by suburb, type and price band</h2>'+table(summaries,list(summaries[0]) if summaries else ['suburb'])
    body+='<h2>Price changes between complete runs</h2>'+table(changes,['suburb','listing_id','old_price','new_price','change_zar','url'])
    body+='<h2>Listing history</h2>'+table(details,['suburb','property_type','asking_price_zar','bedrooms','bathrooms','advertised_size_m2','advertised_status','observed_span_days','first_observed','last_observed','url'])
    body+='<h2>Not observed — not assumed sold</h2>'+table(missing,['suburb','listing_id','price','url'])
    body+='<h2>Weekly trend</h2>'+table(trends,['date','suburb','type','price_band','observed_listings','median_asking_price'])
    body+='<h2>Collection log</h2>'+table(runs,['started','complete','count','reason'])
    style='body{font:15px Arial;margin:30px;color:#183248;background:#f6f8fb}table{border-collapse:collapse;background:white;display:block;overflow:auto;max-height:550px}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left;min-width:90px}th{background:#183248;color:white;position:sticky;top:0}tr:nth-child(even){background:#edf3f7}h2{margin-top:35px}input{padding:12px;width:350px}.warning{background:#ffdfaa;padding:15px}td{max-width:360px;overflow-wrap:anywhere}'
    (output/'dashboard.html').write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Property market monitor</title><style>'+style+'</style></head><body>'+body+'</body></html>',encoding='utf-8')
    return payload

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report-only',action='store_true');ap.add_argument('--import-csv',type=Path)
    ap.add_argument('--scheduled',action='store_true');ap.add_argument('--url',default=propscrape.START)
    ap.add_argument('--delay',type=float,default=60);ap.add_argument('--max-pages',type=int,default=100)
    ap.add_argument('--data-dir',type=Path,default=ROOT/'data');ap.add_argument('--output',type=Path,default=ROOT/'output')
    a=ap.parse_args()
    if a.delay<0 or a.max_pages<1: ap.error('Invalid delay or page limit')
    if not a.url.startswith(propscrape.BASE+'/for-sale/'): ap.error('Use a Property24 for-sale search URL')
    a.data_dir.mkdir(parents=True,exist_ok=True)
    lock=a.data_dir/'run.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        print('Another run may be active. If it crashed, remove data/run.lock after confirming it has stopped.');return 1
    os.close(fd)
    db=None
    try:
        db=connect(a.data_dir/'market.sqlite3')
        if a.import_csv:
            with a.import_csv.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
            dates=[r['observed_at'] for r in rows if r.get('observed_at')]
            stamp=min(dates) if dates else now()
            if not db.execute('SELECT 1 FROM runs WHERE scope=? AND started=?',(a.url,stamp)).fetchone():
                save_run(db,rows,{'complete':False,'stop_reason':'CSV baseline: historical coverage unverified'},a.url,stamp)
        elif not a.report_only:
            last=db.execute('SELECT started FROM runs WHERE scope=? ORDER BY id DESC LIMIT 1',(a.url,)).fetchone()
            if a.scheduled and last and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(last[0])).total_seconds()<6*86400:
                print('Recent collection attempt found; skipping to avoid repeated requests.');return 0
            stamp=now(); cache=a.data_dir/'pages'/stamp.replace(':','-')
            try: rows,coverage=propscrape.run(SimpleNamespace(url=a.url,delay=a.delay,max_pages=a.max_pages,cache=cache))
            except Exception as e: rows=[];coverage={'complete':False,'stop_reason':str(e)}
            save_run(db,rows,coverage,a.url,stamp)
            with db:
                backup=sqlite3.connect(a.data_dir/'market.backup.sqlite3');db.backup(backup);backup.close()
            report(db,a.output,a.url)
            print(json.dumps(coverage,indent=2));print('Dashboard:',a.output/'dashboard.html')
            return 0 if coverage['complete'] else 1
        report(db,a.output,a.url);return 0
    finally:
        if db: db.close()
        lock.unlink(missing_ok=True)

if __name__=='__main__': sys.exit(main())
