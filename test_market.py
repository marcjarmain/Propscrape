import json
import tempfile
import unittest
from pathlib import Path
from market import import_snapshot, report

class HistoryTests(unittest.TestCase):
    def test_price_change_and_incomplete_no_disappearance(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"test.db"
            path=Path(d)/"snapshot.json"
            def load(rows,complete=True):
                doc={"coverage":{"complete":complete,"pages":[{"url":"example","cards":len(rows)}],"stop_reason":"complete" if complete else "blocked"},
                     "listings":[dict(listing_id=str(x[0]),url="https://www.property24.com/"+str(x[0]),
                        search_url="https://www.property24.com/for-sale/test",
                        observed_at="2026-11-09T10:00:00+00:00",asking_price_zar=x[1],suburb="Rondebosch")
                                 for x in rows]}
                path.write_text(json.dumps(doc))
                import_snapshot(path,db)
            load([(1001,7000000),(1002,8000000)])
            load([(1001,6500000)],False)
            state=report(db)
            self.assertEqual(state["totals"]["price_changes"],1)
            self.assertEqual(state["totals"]["not_seen"],0)
            load([(1001,6500000)],True)
            state=report(db)
            self.assertEqual(state["totals"]["not_seen"],0) # compares to immediately preceding crawl
            self.assertEqual(state["brackets"][3]["count"],1)

if __name__=="__main__":unittest.main()
