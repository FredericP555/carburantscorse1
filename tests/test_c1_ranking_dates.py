import datetime as dt
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import c1_last_date
class C1RankingDateTests(unittest.TestCase):
    def test_offset_fixture_for_latest_complete_week(self):
        origin=dt.date(2022,1,1)
        self.assertEqual((dt.date(2026,8,31)-origin).days,1703)
        self.assertEqual((dt.date(2026,9,6)-origin).days,1709)
    def test_latest_daily_date_uses_actual_valid_rows(self):
        payload={'G':{'corse':{'d':[[1708,2.24],[1709,2.25],[1710,None]]}},'S':{'corse':{'d':[[1708,1.99],[1709,None]]}}}
        self.assertEqual(c1_last_date.latest_daily_date(payload),'2026-09-06')
    def test_attach_replaces_stale_metadata(self):
        payload={'G':{'corse':{'d':[[1709,2.25]]}},'S':{'corse':{'d':[[1708,1.99]]}}}
        self.assertEqual(c1_last_date.attach_last_date({'last_date':'2026-08-23'},payload)['last_date'],'2026-09-06')
    def test_validation_rejects_stale_metadata(self):
        payload={'meta':{'last_date':'2026-08-23'},'G':{'corse':{'d':[[1709,2.25]]}},'S':{'corse':{'d':[[1708,1.99]]}}}
        with self.assertRaisesRegex(ValueError,'meta.last_date mismatch'): c1_last_date.validate_last_date(payload)
    def test_frontend_uses_utc_offsets(self):
        src=(ROOT/'app.js').read_text(encoding='utf-8')
        self.assertIn('const ORIGIN_MS = Date.UTC(2022,0,1);',src)
        self.assertIn('new Date(ORIGIN_MS + off*DAY_MS)',src)
        self.assertNotIn('d.setDate(d.getDate()+n)',src)
    def test_ranking_uses_daily_series_not_meta_last_date(self):
        src=(ROOT/'freshness.js').read_text(encoding='utf-8')
        self.assertIn('const maxDate=daily.length?offsetToDate(daily[daily.length-1][0]):null;',src)
        self.assertNotIn('(DATA.meta&&DATA.meta.last_date)||(daily.length',src)
if __name__=='__main__': unittest.main()
