from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rotterdam_corse_shared_v2 as r


class RotterdamCorseSharedT(unittest.TestCase):
    def files(self, daily_value=0.769):
        observed = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        observed.write('date,rotterdam_eur_l\n')
        for d, v in [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-29', 0.783), ('2026-06-01', 0.766), ('2026-06-02', 0.757),
        ]:
            observed.write(f'{d},{v}\n')
        observed.close()
        daily = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        daily.write('date,rotterdam_eur_l,rotterdam_observed,rotterdam_carried\n')
        daily.write(f'2026-08-19,{daily_value},True,False\n')
        daily.close()
        self.addCleanup(lambda: Path(observed.name).unlink(missing_ok=True))
        self.addCleanup(lambda: Path(daily.name).unlink(missing_ok=True))
        return observed.name, daily.name

    def test_canonical_corsica_calibration(self):
        observed, _ = self.files()
        c = r.calibration_2026(observed)
        self.assertEqual(c['r1_source_dates'], ['2026-04-03', '2026-04-06', '2026-04-07'])
        self.assertAlmostEqual(c['r1'], 1.0486666667, places=9)
        self.assertAlmostEqual(c['k'], 0.7329942784, places=9)
        self.assertAlmostEqual(c['r2'], 0.7686666667, places=9)

    def test_shared_metadata_has_integrity_hashes(self):
        observed, daily = self.files()
        meta = r.shared_metadata(observed, daily)
        self.assertTrue(meta['single_download'])
        self.assertEqual(len(meta['observed_sha256']), 64)
        self.assertEqual(len(meta['daily_sha256']), 64)
        self.assertEqual(meta['corsica_calibration']['territory'], 'corsica')
        self.assertIn('R2 does not define shield effectiveness', meta['runtime_rule'])

    def test_runtime_r2_comparator(self):
        observed, daily = self.files(0.769)
        self.assertTrue(r.constraining_on(date(2026, 8, 19), observed_file=observed, daily_file=daily))
        observed2, daily2 = self.files(0.760)
        self.assertFalse(r.constraining_on(date(2026, 8, 19), observed_file=observed2, daily_file=daily2))

    def test_missing_daily_value_fails_closed(self):
        observed, daily = self.files()
        with self.assertRaises(ValueError):
            r.constraining_on(date(2026, 8, 20), observed_file=observed, daily_file=daily)


if __name__ == '__main__':
    unittest.main()
