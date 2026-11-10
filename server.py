"""Read-only local dashboard. Starting it NEVER starts a collection."""
import argparse, datetime as dt, json, os, sqlite3, subprocess, sys, time, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PORT=8768
IDENTITY='propscrape-dashboard-v1'

def read_status(root=ROOT):
    root=Path(root); path=root/'data'/'market.sqlite3'
    result={'service':IDENTITY,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
      'database_exists':path.exists(),'database_bytes':path.stat().st_size if path.exists() else 0,
      'backup_exists':(root/'data'/'market.backup.sqlite3').exists(),
      'lock_present':(root/'data'/'run.lock').exists(),'runs':[], 'suburbs':[],
      'listings':[], 'total_runs':0,'total_observations':0,'unique_listing_ids':0,
      'snapshot':None,'alerts':[], 'last_job':None}
    state=root/'data'/'last_job.json'
    if state.exists():
        try: result['last_job']=json.loads(state.read_text(encoding='utf-8'))
        except (ValueError,OSError): result['alerts'].append({'level':'warning','text':'Could not read the last scheduled-job status.'})
    if result['last_job'] and result['last_job'].get('exit_code') not in (0,None):
        result['alerts'].append({'level':'error','text':'Last scheduled job failed. Open the latest job log below.'})
    if result['lock_present']:
        result['alerts'].append({'level':'warning','text':'Collection lock exists: a job may be running. If this remains after a crash, check the Python process before removing data/run.lock.'})
    if not path.exists():
        result['alerts'].append({'level':'warning','text':'No history database yet. Run setup_weekly.bat to import your existing output/listings.csv and set up collection.'})
        return result
    db=None
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3);db.row_factory=sqlite3.Row
        result['total_runs']=db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        result['total_observations']=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        result['unique_listing_ids']=db.execute('SELECT COUNT(DISTINCT listing_id) FROM observations').fetchone()[0]
        result['runs']=[dict(r) for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 20')]
        latest=result['runs'][0] if result['runs'] else None
        if not latest:
            result['alerts'].append({'level':'warning','text':'The database has no collection records yet.'});return result
        scope=latest['scope']
        full=db.execute('SELECT * FROM runs WHERE complete=1 AND scope=? ORDER BY id DESC LIMIT 1',(scope,)).fetchone()
        selected=dict(full) if full else dict(db.execute('SELECT * FROM runs WHERE count>0 AND scope=? ORDER BY id DESC LIMIT 1',(scope,)).fetchone() or latest)
        result['snapshot']=selected
        if not latest['complete']:
            imported=str(latest['reason']).startswith('CSV baseline')
            result['alerts'].append({'level':'warning' if imported else 'error','text':('Imported baseline: coverage unverified.' if imported else 'Latest collection incomplete: '+str(latest['reason']))})
        if not full: result['alerts'].append({'level':'warning','text':'No complete collection yet. Listing counts below are partial; changes cannot be inferred.'})
        stamp=dt.datetime.fromisoformat(selected['started']);stamp=stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.timezone.utc)
        age=(dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()/86400
        if age>8: result['alerts'].append({'level':'warning','text':f'Displayed data is {int(age)} days old. Check the weekly task and collection log.'})
        history={r['listing_id']:dict(r) for r in db.execute('SELECT listing_id,MIN(r.started) AS first_seen,MAX(r.started) AS last_seen,COUNT(*) AS observations FROM observations o JOIN runs r ON r.id=o.run_id WHERE r.scope=? GROUP BY listing_id',(scope,))}
        groups={};missing_price=0
        for o in db.execute('SELECT * FROM observations WHERE run_id=?',(selected['id'],)):
            v=json.loads(o['data']);h=history[o['listing_id']]
            first=dt.datetime.fromisoformat(h['first_seen']);last=dt.datetime.fromisoformat(h['last_seen'])
            item={'listing_id':o['listing_id'],'suburb':v.get('suburb') or 'Unknown',
              'type':v.get('property_type') or 'unknown','price':o['price'],'beds':v.get('bedrooms'),
              'baths':v.get('bathrooms'),'size':v.get('advertised_size_m2'),
              'status':o['status'],'url':v.get('url'),'days_observed':max(0,(last-first).days),
              'first_seen':h['first_seen'],'last_seen':h['last_seen']}
            result['listings'].append(item)
            group=groups.setdefault(item['suburb'],{'suburb':item['suburb'],'listings':0,'houses':0,'under_offer':0,'sold_unavailable':0})
            group['listings']+=1;group['houses']+=item['type']=='house'
            group['under_offer']+=o['status']=='advertised under offer'
            group['sold_unavailable']+=o['status']=='advertised sold/unavailable'
            missing_price+=o['price'] is None
        result['suburbs']=sorted(groups.values(),key=lambda r:(-r['listings'],r['suburb']))
        result['listings'].sort(key=lambda r:(r['suburb'],r['price'] if r['price'] is not None else float('inf')))
        result['missing_prices']=missing_price
        if not result['backup_exists']: result['alerts'].append({'level':'warning','text':'No database backup found. The collector creates one after its next attempt.'})
    except (sqlite3.Error,ValueError,TypeError,KeyError) as e:
        result['alerts'].append({'level':'error','text':'Database could not be fully read: '+str(e)})
    finally:
        if db: db.close()
    return result

class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,kind):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        root=self.server.root
        try:
            if self.path=='/health': return self.send(200,json.dumps({'service':IDENTITY,'root':str(root)}).encode(),'application/json')
            if self.path=='/api/status': return self.send(200,json.dumps(read_status(root),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if self.path in ('/','/dashboard.html'): return self.send(200,(root/'dashboard.html').read_bytes(),'text/html; charset=utf-8')
            if self.path=='/api/log':
                logs=sorted((p for p in (root/'data'/'logs').glob('*.log') if p.name!='server.log'),key=lambda p:p.stat().st_mtime)
                if not logs: return self.send(200,b'No scheduled-job logs yet.','text/plain; charset=utf-8')
                with logs[-1].open('rb') as f:
                    f.seek(max(0,logs[-1].stat().st_size-16000));data=f.read()
                return self.send(200,data,'text/plain; charset=utf-8')
            exports={'/download/market.json':'market.json','/download/listings.csv':'listings_history.csv','/download/suburbs.csv':'suburb_summary.csv','/download/trends.csv':'weekly_trends.csv'}
            if self.path in exports:
                return self.send(200,(root/'output'/exports[self.path]).read_bytes(),'application/octet-stream')
            self.send(404,b'Not found','text/plain')
        except OSError as e: self.send(503,('File unavailable: '+str(e)).encode(),'text/plain; charset=utf-8')
    def log_message(self,*args): pass

def health(port):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}/health',timeout=1) as response:
            return json.load(response)
    except (OSError,ValueError): return None

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--open',action='store_true');ap.add_argument('--port',type=int,default=PORT)
    a=ap.parse_args();url=f'http://127.0.0.1:{a.port}/'
    if a.open:
        existing=health(a.port)
        if existing and (existing.get('service')!=IDENTITY or existing.get('root')!=str(ROOT)):
            raise SystemExit('Port is serving another app or another Propscrape copy; close that server first.')
        if not existing:
            logs=ROOT/'data'/'logs';logs.mkdir(parents=True,exist_ok=True)
            options={'cwd':ROOT,'stdin':subprocess.DEVNULL}
            if os.name=='nt': options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
            else: options['start_new_session']=True
            with (logs/'server.log').open('ab') as f:
                subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(a.port)],stdout=f,stderr=f,**options)
            for _ in range(40):
                existing=health(a.port)
                if existing: break
                time.sleep(.25)
        if not existing or existing.get('service')!=IDENTITY or existing.get('root')!=str(ROOT): raise SystemExit('Server did not start. Check data/logs/server.log and whether port 8768 is occupied.')
        webbrowser.open(url);return
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.root=ROOT
    try: server.serve_forever()
    finally: server.server_close()

if __name__=='__main__': main()
