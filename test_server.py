import json, sqlite3, tempfile, threading, unittest, urllib.request
from pathlib import Path
from unittest.mock import patch
import market, propscrape, server

class DashboardTests(unittest.TestCase):
    def test_empty_does_not_create_db_or_scrape(self):
        with tempfile.TemporaryDirectory() as d, patch.object(propscrape,'fetch',side_effect=AssertionError('Network forbidden')):
            r=server.read_status(Path(d));self.assertFalse(r['database_exists']);self.assertTrue(r['alerts'])
            self.assertFalse((Path(d)/'data').exists())
    def test_failed_run_preserves_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=market.connect(root/'data'/'market.sqlite3')
            market.save_run(db,[{'listing_id':'123','price_text':'R 6 000 000','suburb':'Wynberg','property_type':'house'}],{'complete':True,'stop_reason':'complete'},'scope')
            market.save_run(db,[],{'complete':False,'stop_reason':'HTTP 403'},'scope');db.close()
            before=(root/'data'/'market.sqlite3').read_bytes()
            with patch.object(propscrape,'fetch',side_effect=AssertionError('Network forbidden')): r=server.read_status(root)
            self.assertEqual(len(r['listings']),1);self.assertEqual(r['listings'][0]['price'],6000000)
            self.assertTrue(any('403' in a['text'] for a in r['alerts']))
            self.assertEqual(before,(root/'data'/'market.sqlite3').read_bytes())
    def test_corrupt_db_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'data'/'market.sqlite3').write_text('broken')
            self.assertTrue(any(a['level']=='error' for a in server.read_status(root)['alerts']))
    def test_http_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'dashboard.html').write_text('Dashboard')
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);http.root=root
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:'+str(http.server_port)
            try:
                self.assertEqual(opener.open(base+'/').read(),b'Dashboard')
                self.assertEqual(json.load(opener.open(base+'/api/status'))['total_runs'],0)
                with self.assertRaises(urllib.error.HTTPError): opener.open(base+'/scrape')
                with self.assertRaises(urllib.error.HTTPError): opener.open(urllib.request.Request(base+'/',data=b'start',method='POST'))
            finally: http.shutdown();http.server_close();thread.join()
if __name__=='__main__': unittest.main()
