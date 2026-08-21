from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import r2_guard_v2 as guard


class R2GuardT(unittest.TestCase):
    def observed_file(self):
        f = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        f.write('date,rotterdam_eur_l\n')
        for d, v in [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-29', 0.783), ('2026-06-01', 0.766), ('2026-06-02', 0.757),
        ]:
            f.write(f'{d},{v}\n')
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def daily_file(self, rows):
        f = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        f.write('date,rotterdam_eur_l\n')
        for d, v in rows:
            f.write(f'{d.isoformat()},{v}\n')
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_first_stale_day_is_declaration_plus_45(self):
        declared = datetime(2026, 6, 1, 8)
        first_stale = date(2026, 7, 16)
        daily = self.daily_file([(first_stale, 0.769)])
        self.assertTrue(guard.stale_price_admissible(
            declared, first_stale,
            observed_file=self.observed_file(), daily_file=daily,
        ))

    def test_breach_at_or_after_j45_locks_old_price(self):
        declared = datetime(2026, 6, 1, 8)
        start = date(2026, 7, 16)
        rows = [
            (start, 0.780),
            (start + timedelta(days=1), 0.760),
            (start + timedelta(days=2), 0.790),
        ]
        self.assertFalse(guard.stale_price_admissible(
            declared, start + timedelta(days=2),
            observed_file=self.observed_file(), daily_file=self.daily_file(rows),
        ))

    def test_new_target_declaration_resets_origin(self):
        # An old declaration could have been locked, but a new official target
        # declaration creates a fresh J0. While it is still <45 days old R2 is irrelevant.
        new_declared = datetime(2026, 8, 10, 8)
        self.assertTrue(guard.stale_price_admissible(
            new_declared, date(2026, 8, 19),
            observed_file=self.observed_file(), daily_file=self.daily_file([]),
        ))

    def test_missing_or_future_declaration_fails_closed(self):
        observed = self.observed_file()
        daily = self.daily_file([])
        self.assertFalse(guard.stale_price_admissible(None, date(2026, 8, 19), observed_file=observed, daily_file=daily))
        self.assertFalse(guard.stale_price_admissible(datetime(2026, 8, 20), date(2026, 8, 19), observed_file=observed, daily_file=daily))


if __name__ == '__main__':
    unittest.main()
