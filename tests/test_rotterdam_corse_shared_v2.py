from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rotterdam_corse_shared_v2 as r


class RotterdamCorseSharedT(unittest.TestCase):
    def observed_file(self, extra_rows=()):
        observed = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        observed.write('date,rotterdam_eur_l\n')
        for d, v in [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-29', 0.783), ('2026-06-01', 0.766), ('2026-06-02', 0.757),
            *extra_rows,
        ]:
            observed.write(f'{d},{v}\n')
        observed.close()
        self.addCleanup(lambda: Path(observed.name).unlink(missing_ok=True))
        return observed.name

    def daily_file(self, rows):
        daily = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        daily.write('date,rotterdam_eur_l,rotterdam_observed,rotterdam_carried\n')
        for d, value in rows:
            daily.write(f'{d.isoformat()},{value},True,False\n')
        daily.close()
        self.addCleanup(lambda: Path(daily.name).unlink(missing_ok=True))
        return daily.name

    def test_2026_reference_episode_calibrates_k(self):
        observed = self.observed_file()
        c = r.calibration_2026(observed)
        self.assertEqual(c['role'], 'baseline_k_calibration')
        self.assertEqual(c['r1_source_dates'], ['2026-04-03', '2026-04-06', '2026-04-07'])
        self.assertAlmostEqual(c['r1'], 1.0486666667, places=9)
        self.assertAlmostEqual(c['k'], 0.7329942784, places=9)
        self.assertAlmostEqual(c['r2'], 0.7686666667, places=9)

    def test_first_2026_phase_reproduces_reference_r2(self):
        c = r.calibration_for_phase(date(2026, 4, 8), self.observed_file())
        self.assertEqual(c['r1_source_dates'], ['2026-04-03', '2026-04-06', '2026-04-07'])
        self.assertAlmostEqual(c['r2'], 0.7686666667, places=9)

    def test_later_effective_phase_uses_three_quotes_immediately_before_it(self):
        observed = self.observed_file(extra_rows=(
            ('2026-09-28', 0.900),
            ('2026-09-29', 0.930),
            ('2026-09-30', 0.960),
        ))
        c = r.calibration_for_phase(date(2026, 10, 1), observed)
        self.assertEqual(c['r1_source_dates'], ['2026-09-28', '2026-09-29', '2026-09-30'])
        self.assertAlmostEqual(c['r1'], 0.930, places=12)
        self.assertAlmostEqual(c['r2'], c['k'] * 0.930, places=12)
        self.assertNotAlmostEqual(c['r2'], 0.7686666667, places=6)

    def test_shared_metadata_describes_dynamic_phase_r2(self):
        observed = self.observed_file()
        daily = self.daily_file([(date(2026, 8, 19), 0.769)])
        meta = r.shared_metadata(observed, daily)
        self.assertTrue(meta['single_download'])
        self.assertEqual(len(meta['observed_sha256']), 64)
        self.assertEqual(len(meta['daily_sha256']), 64)
        self.assertEqual(meta['corsica_calibration']['territory'], 'corsica')
        self.assertIn('last 3 actually observed', meta['runtime_r2_rule']['r1_policy'])
        self.assertIn('current effective-shield cap phase', meta['runtime_rule'])

    def test_phase_specific_r2_boundary_is_greater_or_equal(self):
        observed = self.observed_file()
        phase_start = date(2026, 4, 8)
        day = date(2026, 8, 19)
        high = self.daily_file([(day, 0.7686666666666667)])
        self.assertTrue(r.admissible_since(
            day, day, phase_started_on=phase_start,
            observed_file=observed, daily_file=high
        ))
        low = self.daily_file([(day, 0.760)])
        self.assertFalse(r.admissible_since(
            day, day, phase_started_on=phase_start,
            observed_file=observed, daily_file=low
        ))

    def test_r2_breach_remains_locked_after_recovery(self):
        observed = self.observed_file()
        phase_start = date(2026, 4, 8)
        start = date(2026, 8, 17)
        daily = self.daily_file([
            (start, 0.780),
            (start + timedelta(days=1), 0.760),
            (start + timedelta(days=2), 0.790),
        ])
        self.assertFalse(r.admissible_since(
            start, date(2026, 8, 19), phase_started_on=phase_start,
            observed_file=observed, daily_file=daily
        ))

    def test_nonfinite_observed_is_rejected(self):
        with self.assertRaises(ValueError):
            r.read_observed(self.observed_file(extra_rows=(('2026-04-04', 'nan'),)))

    def test_nonfinite_daily_is_rejected(self):
        with self.assertRaises(ValueError):
            r.read_daily_values(self.daily_file([(date(2026, 8, 19), 'inf')]))

    def test_missing_daily_value_fails_closed(self):
        observed = self.observed_file()
        daily = self.daily_file([(date(2026, 8, 19), 0.769)])
        with self.assertRaises(ValueError):
            r.admissible_since(
                date(2026, 8, 19), date(2026, 8, 20),
                phase_started_on=date(2026, 4, 8),
                observed_file=observed, daily_file=daily
            )


if __name__ == '__main__':
    unittest.main()
