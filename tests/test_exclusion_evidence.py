from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from a4c_common.exclusion_evidence import decision_row, summarize, write_evidence


class ExclusionEvidenceTests(unittest.TestCase):
    def row(self, sid='1', eligible=True, category='network'):
        return decision_row(date(2026,11,15), 'BdR', sid, 'Gazole', 'Test', category,
            datetime(2026,11,14), 2.0, SimpleNamespace(eligible=eligible, reason='normal_45j' if eligible else 'rupture_active'), 1)

    def test_scope_counts_do_not_treat_gms_as_reliability_exclusion(self):
        rows=[self.row(),self.row('2',False),self.row('3',True,'gms')]
        totals={r['scope']:r for r in summarize(rows)}
        self.assertEqual((totals['all']['candidates'],totals['all']['retained'],totals['all']['excluded']),(3,2,1))
        self.assertEqual((totals['network']['candidates'],totals['network']['retained'],totals['network']['excluded']),(2,1,1))
        self.assertEqual(totals['all']['excluded_by_reason'],{'rupture_active':1})
        with self.assertRaises(ValueError): summarize([rows[0],rows[0]])

    def test_export_error_is_explicit_and_does_not_change_baseline(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); baseline=root/'data.json'; baseline.write_text('untouched')
            with self.assertWarns(RuntimeWarning):
                result=write_evidence(root,'c1',[self.row(),self.row()],source_files=[baseline])
            self.assertEqual(result['status'],'error')
            self.assertFalse((root/'outputs/c1-exclusions.csv.gz').exists())
            self.assertEqual(baseline.read_text(),'untouched')

    def test_export_preserves_inputs_and_marks_unreconciled_calculation(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); baseline=root/'data.json'; baseline.write_text('untouched')
            rows=[self.row()]
            with patch('a4c_common.exclusion_evidence.subprocess.run',return_value=SimpleNamespace(stdout='a'*40)):
                result=write_evidence(root,'c1',rows,source_files=[baseline])
            self.assertEqual(result['status'],'ok')
            report=json.loads((root/result['manifest']).read_text())
            self.assertFalse(report['publication_reconciled'])
            self.assertEqual(len(report['csv_sha256']),64)
            self.assertEqual(baseline.read_text(),'untouched')
            self.assertEqual(rows,[self.row()])

class C1ObserverTests(unittest.TestCase):
    def test_observer_does_not_change_calculation_or_event_counts(self):
        import pandas as pd
        from scripts import build_c1_v2_candidate as b
        day=date(2026,11,15)
        def parse(year,declarations,events,dates):
            declarations[('20000001','corse','Gazole')]=[(datetime(2026,11,14),2.0)]
            dates.append(day)
        with TemporaryDirectory() as folder:
            registry=Path(folder)/'brands.json'; registry.write_text('{"stations":{}}')
            with patch.object(b,'parse_year',side_effect=parse), patch.object(b,'CORSE_REGISTRY',registry), patch.object(b.bouclier_detector,'metadata',return_value={}), patch.object(b.shield_phase_v2,'with_cap_phases',return_value={}), patch.object(b.shield_phase_v2,'phase_for_day',return_value=None):
                before,a=b.build_v2_daily([2026],day,day)
                rows=[]; after,z=b.build_v2_daily([2026],day,day,decision_rows=rows)
        pd.testing.assert_frame_equal(before,after)
        self.assertEqual(a,z)
        self.assertEqual(len(rows),1) # no invented SP95 candidate
        self.assertTrue(rows[0]['eligible'])
