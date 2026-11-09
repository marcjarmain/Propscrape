#!/usr/bin/env python3
"""Collect Property24 search cards and export a portable comparison dataset."""
import argparse, csv, datetime, json, re, sys, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://www.property24.com'
START = BASE + '/for-sale/alias/southern-suburbs/25/western-cape/9'
UA = 'PropScrape/1.0 (personal property comparison)'
REGIONS = {
    'Southern Suburbs': ['Bishopscourt','Claremont','Claremont Upper','Constantia','Constantia Upper','Diep River','Fernwood','Grassy Park','Harfield Village','Heathfield','Kenilworth','Kenilworth Upper','Kirstenhof','Lakeside','Lotus River','Meadowridge','Mowbray','Muizenberg','Newlands','Observatory','Ottery','Plumstead','Retreat','Rondebosch','Rondebosch East','Rosebank','Salt River','Southfield','Steenberg','Tokai','Wynberg','Wynberg Upper','Zwaanswyk'],
    'Atlantic Seaboard': ['Bantry Bay','Bakoven','Camps Bay','Clifton','Fresnaye','Green Point','Hout Bay','Llandudno','Mouille Point','Sea Point','Three Anchor Bay'],
    'City Bowl': ['Bo Kaap','Cape Town City Centre','De Waterkant','Devils Peak','Gardens','Higgovale','Oranjezicht','Schotsche Kloof','Tamboerskloof','Vredehoek','Woodstock','Zonnebloem'],
    'Northern Suburbs': ['Bellville','Boston','Brackenfell','Durbanville','Edgemead','Goodwood','Kenridge','Kraaifontein','Panorama','Parow','Plattekloof','Welgemoed'],
    'West Coast': ['Blouberg','Bloubergstrand','Big Bay','Melkbosstrand','Milnerton','Parklands','Sunningdale','Table View'],
    'South Peninsula': ['Fish Hoek','Glencairn','Kalk Bay','Kommetjie','Noordhoek','Scarborough','Simons Town','St James','Sunnydale'],
}
def region(s):
    norm = lambda x: re.sub(r'[^a-z0-9]', '', (x or '').lower())
    for group, suburbs in REGIONS.items():
        if norm(s) in {norm(x) for x in suburbs}: return group
    return 'Unclassified'

class Node:
    def __init__(self, tag='', attrs=()): self.tag=tag; self.attrs=dict(attrs); self.children=[]
    def text(self): return ' '.join(x.text() if isinstance(x,Node) else x for x in self.children).strip()
    def walk(self):
        yield self
        for x in self.children:
            if isinstance(x,Node): yield from x.walk()
    def has(self,c): return c in self.attrs.get('class','').split()
    def find(self,c): return next((n for n in self.walk() if n.has(c)),None)
class Parser(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self): super().__init__(convert_charrefs=True); self.root=Node(); self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs); self.stack[-1].children.append(n)
        if tag not in self.VOID: self.stack.append(n)
    def handle_startendtag(self,tag,attrs): self.handle_starttag(tag,attrs); self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag: self.stack=self.stack[:i]; break
    def handle_data(self,data): self.stack[-1].children.append(data)
def number(s):
    if not s: return None
    m=re.search(r'\d[\d\s\u00a0]*(?:[.,]\d+)?',s)
    if not m: return None
    v=re.sub(r'\s','',m.group()).replace(',','.')
    try: return float(v) if '.' in v else int(v)
    except ValueError: return None

def parse(html, page_url):
    p=Parser(); p.feed(html); out=[]
    tiles=[n for n in p.root.walk() if n.has('p24_regularTile') or n.has('p24_proTile')]
    for t in tiles:
        links=[n.attrs.get('href','') for n in t.walk() if n.tag=='a']
        href=next((x for x in links if re.search(r'/for-sale/.*/\d{7,}(?:[/?]|$)',x)),None)
        if not href: continue
        def value(c):
            n=t.find(c); return re.sub(r'\s+',' ',n.text()).strip() if n else ''
        title=value('p24_title'); suburb=value('p24_location'); price=value('p24_price')
        feats={}
        for f in (n for n in t.walk() if n.has('p24_featureDetails')):
            labels=' '.join([f.text()] + [str(v) for n in f.walk() for k,v in n.attrs.items() if k in ('title','alt','class','aria-label')]).lower()
            val=number(f.text())
            for k,patterns in {'bedrooms':['bedroom','bed '], 'bathrooms':['bathroom','bath '], 'parking':['parking','garage','car '], 'size_m2':['size','erf','floor','m²','m2']}.items():
                if any(x in labels for x in patterns) and val is not None: feats.setdefault(k,val)
        match=re.search(r'(house|apartment|flat|townhouse|vacant land|farm|commercial)', title, re.I)
        rawsize=feats.pop('size_m2',None)
        url=urllib.parse.urljoin(BASE,href).split('?')[0]
        out.append({'listing_id':url.rstrip('/').split('/')[-1], 'url':url,'source':'Property24','search_url':page_url,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'asking_price_zar':number(price) if re.search(r'\d',price) else None,'price_text':price,'title':title,'suburb':suburb,'region':region(suburb),'property_type':match.group(1).lower() if match else None,'bedrooms':feats.get('bedrooms'),'bathrooms':feats.get('bathrooms'),'parking':feats.get('parking'),'advertised_size_m2':rawsize,'size_type':'unspecified' if rawsize else None,'erf_m2':None,'floor_m2':None,'description':value('p24_excerpt')})
    nexturl=None
    for n in p.root.walk():
        if n.tag=='a' and (n.text().strip().lower()=='next' or n.attrs.get('rel')=='next') and n.attrs.get('href'):
            nexturl=urllib.parse.urljoin(page_url,n.attrs['href']); break
    return out,nexturl

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=30) as r:
        if urllib.parse.urlparse(r.geturl()).hostname != 'www.property24.com': raise RuntimeError('Unexpected redirect; stopped')
        return r.read().decode('utf-8','replace')
def run(args):
    robot=urllib.robotparser.RobotFileParser(); robot.set_url(BASE+'/robots.txt')
    try:
        robot.parse(fetch(BASE+'/robots.txt').splitlines())
    except Exception as e: raise RuntimeError('Could not check robots.txt; stopped: '+str(e))
    listings={}; pages=[]; url=args.url; seen=set(); reason='complete'
    while url and url not in seen and len(pages)<args.max_pages:
        if urllib.parse.urlparse(url).hostname!='www.property24.com': reason='unexpected next-page domain'; break
        if not robot.can_fetch(UA,url): reason='robots.txt disallows '+url; break
        seen.add(url)
        try: html=fetch(url)
        except (urllib.error.URLError,RuntimeError) as e: reason='fetch failed: '+str(e); break
        rows,nxt=parse(html,url)
        if not rows: reason='no listing cards recognised; page may have changed or blocked access'; break
        for row in rows: listings[row['listing_id']]=row
        pages.append({'url':url,'cards':len(rows)})
        print(f'Page {len(pages)}: {len(rows)} cards; {len(listings)} unique',flush=True)
        url=nxt
        if url and len(pages)<args.max_pages: time.sleep(args.delay)
    if url and len(pages)>=args.max_pages: reason='page limit reached; coverage incomplete'
    return list(listings.values()), {'pages':pages,'stop_reason':reason,'complete':reason=='complete','unique_listings':len(listings)}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url',default=START,help='Property24 for-sale region search URL')
    ap.add_argument('--max-pages',type=int,default=100); ap.add_argument('--delay',type=float,default=2)
    ap.add_argument('--subject',default='subject.json'); ap.add_argument('--output',default='output')
    a=ap.parse_args()
    if a.max_pages<1 or a.delay<0: ap.error('Invalid page limit or delay')
    if urllib.parse.urlparse(a.url).scheme!='https' or urllib.parse.urlparse(a.url).hostname!='www.property24.com': ap.error('Use an https://www.property24.com URL')
    subject=json.loads(Path(a.subject).read_text(encoding='utf-8'))
    rows,coverage=run(a)
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    data={'subject':subject,'coverage':coverage,'notes':['Asking prices, not achieved sale prices.','Area shown on a search card is not reliably identified as erf or floor area.','Suburb groupings are indicative and incomplete; unclassified areas are retained.','Listings are not automatically verified as comparable.'],'listings':rows}
    (out/'comparison.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    if rows:
        with (out/'listings.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    print(json.dumps(coverage,indent=2)); print('Saved to',out)
    if not rows or not coverage['complete']: return 1
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,ValueError,RuntimeError) as e: print('Error:',e,file=sys.stderr); sys.exit(1)
