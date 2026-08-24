from datetime import date
import unittest

import pandas as pd

from a4c_common.ufip import expand_daily


class UfipCarryGuardTests(unittest.TestCase):
    def test_weekend_is_carried(self):
        obs = pd.DataFrame([
            {"date": date(2026, 8, 14), "rotterdam_eur_l": 0.961},
            {"date": date(2026, 8, 17), "rotterdam_eur_l": 0.970},
        ])
        daily = expand_daily(obs, date(2026, 8, 14), date(2026, 8, 17)).set_index("date")
        self.assertAlmostEqual(float(daily.loc[date(2026, 8, 15), "rotterdam_eur_l"]), 0.961)
        self.assertAlmostEqual(float(daily.loc[date(2026, 8, 16), "rotterdam_eur_l"]), 0.961)
        self.assertTrue(bool(daily.loc[date(2026, 8, 15), "rotterdam_carried"]))
        self.assertTrue(bool(daily.loc[date(2026, 8, 16), "rotterdam_carried"]))

    def test_missing_week_is_not_manufactured(self):
        obs = pd.DataFrame([
            {"date": date(2026, 8, 14), "rotterdam_eur_l": 0.961},
        ])
        daily = expand_daily(obs, date(2026, 8, 14), date(2026, 8, 24)).set_index("date")
        self.assertAlmostEqual(float(daily.loc[date(2026, 8, 17), "rotterdam_eur_l"]), 0.961)
        self.assertTrue(pd.isna(daily.loc[date(2026, 8, 18), "rotterdam_eur_l"]))
        self.assertTrue(pd.isna(daily.loc[date(2026, 8, 24), "rotterdam_eur_l"]))
        self.assertFalse(bool(daily.loc[date(2026, 8, 18), "rotterdam_carried"]))


if __name__ == "__main__":
    unittest.main()
