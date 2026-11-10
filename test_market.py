import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import market, propscrape

def row(lid,price='R 7 995 000 4 Bedroom House in Claremont',suburb='Claremont'):
    return {'listing_id':lid,'price_text':price,'suburb':suburb,'bedrooms':4,'description':'','url':'https://www.property24.com/for-sale/example/'+lid}
class Tests(unittest.TestCase):
    def test_price(self):
        for text,want in [('R 7 995 000 4 Bedroom House',7995000),('R 7,995,000.00',7995000),('R 7995000',7995000),('POA 8 Bedroom House',None),('Auction 3 Bedroom House',None),('R 2 199 000',2199000)]:
            self.assertEqual(propscrape.asking_price(text),want)
    def test_type_status(self):
        r=market.normalise(row('1')); self.assertEqual(r['property_type'],'house')
        self.assertEqual(r['advertised_status'],'unknown')
        r['description']='UNDER OFFER'; self.assertEqual(market.normalise(r)['advertised_status'],'advertised under offer')
        r['description']='sold furnished'; self.assertEqual(market.normalise(r)['advertised_status'],'unknown')
    def test_history_partial_scope_and_changes(self):
        with tempfile.TemporaryDirectory() as d:
            db=market.connect(Path(d)/'db.sqlite3'); full={'complete':True,'stop_reason':'complete'}
            market.save_run(db,[row('1'),row('2')],full,'scope','2026-11-01T00:00:00+00:00')
            market.save_run(db,[],{'complete':False,'stop_reason':'blocked'},'scope','2026-11-03T00:00:00+00:00')
            p=market.report(db,Path(d)/'out','scope');self.assertEqual(len(p['listings']),2);self.assertEqual(p['missing'],[])
            market.save_run(db,[row('1','R 7 500 000'),row('3')],full,'scope','2026-11-08T00:00:00+00:00')
            market.save_run(db,[row('9')],full,'other','2026-11-08T00:00:00+00:00')
            p=market.report(db,Path(d)/'out','scope')
            self.assertEqual(p['price_changes'][0]['change_zar'],-495000)
            self.assertEqual(p['missing'][0]['listing_id'],'2')
            self.assertEqual(p['listings'][0]['observed_span_days'],7)
            self.assertEqual(len(p['listings']),2);self.assertEqual(p['listings'][1]['new_since_previous_complete'],True)
            db.close()
    def test_repeated_pagination_is_incomplete(self):
        args=SimpleNamespace(url=propscrape.START,max_pages=2,delay=0)
        with patch.object(propscrape,'fetch',return_value='User-agent: *\nAllow: /'),patch.object(propscrape,'parse',return_value=([row('1')],propscrape.START)):
            rows,c=propscrape.run(args)
            self.assertFalse(c['complete']);self.assertEqual(len(rows),1)
    def test_no_extra_request_after_error(self):
        args=SimpleNamespace(url=propscrape.START,max_pages=5,delay=0)
        with patch.object(propscrape,'fetch',side_effect=['User-agent: *\nAllow: /',OSError('blocked')]) as f:
            rows,c=propscrape.run(args)
            self.assertFalse(c['complete']);self.assertEqual(f.call_count,2)
    def test_subject_size_not_invented(self):
        r=market.normalise(row('1'));self.assertIsNone(r['erf_m2']);self.assertIsNone(r['floor_m2'])
if __name__=='__main__': unittest.main()
