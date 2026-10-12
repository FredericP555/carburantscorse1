"""Regression tests for C1 editorial calculations; no fuel-series mutation."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import enrich_data_meta as editorial


def synthetic_data(first=date(2022, 1, 1), last=date(2027, 1, 15), omit=()):
    result = {}
    for short in ("G", "S"):
        corse = []
        mainland = []
        day = first
        while day <= last:
            if day not in omit:
                offset = (day - date(2022, 1, 1)).days
                gap = 0.15 if date(2026, 9, 28) <= day <= date(2026, 10, 4) else 0.10
                corse.append([offset, 2.0, round(1.5 + gap, 4)])
                mainland.append([offset, 1.8, 1.5])
            day += timedelta(days=1)
        result[short] = {"corse": {"d": corse}, "moy_regions": {"d": mainland}}
    return result


BOUCLIER = {
    "Gazole": {"ranges": [{"d1": "2026-04-01", "d2": "2026-12-31"}]},
    "SP95": {"ranges": [{"d1": "2026-03-12", "d2": "2026-12-31"}]},
}


class C1EditorialAutomationTests(unittest.TestCase):
    def test_historical_action_calendar_is_preserved(self):
        self.assertTrue(editorial.inside(date(2022, 9, 1), editorial.editorial_calendar_for_year(BOUCLIER, 2022)))
        self.assertFalse(editorial.inside(date(2022, 8, 31), editorial.editorial_calendar_for_year(BOUCLIER, 2022)))
        self.assertTrue(editorial.inside(date(2023, 3, 1), editorial.editorial_calendar_for_year(BOUCLIER, 2023)))
        self.assertFalse(editorial.inside(date(2025, 5, 1), editorial.editorial_calendar_for_year(BOUCLIER, 2025)))
        self.assertTrue(editorial.inside(date(2026, 3, 20), editorial.editorial_calendar_for_year(BOUCLIER, 2026)))
        self.assertFalse(editorial.inside(date(2026, 3, 1), editorial.editorial_calendar_for_year(BOUCLIER, 2026)))

    def test_annual_history_and_new_year(self):
        data = synthetic_data()
        hist_2026 = editorial.completed_annual_gaps(data, "S", 2026, BOUCLIER)
        self.assertEqual([x["year"] for x in hist_2026], [2022, 2023, 2024, 2025])
        self.assertEqual(hist_2026[0]["outside_total_action_days"], 243)
        self.assertEqual(hist_2026[0]["outside_total_action_gap"], 10.0)
        hist_2027 = editorial.completed_annual_gaps(data, "S", 2027, BOUCLIER)
        self.assertEqual(hist_2027[-1]["year"], 2026)
        self.assertLess(hist_2027[-1]["outside_total_action_days"], 180)
        self.assertEqual(hist_2027[-1]["outside_total_action_gap"], 10.0)

    def test_two_complete_weeks(self):
        data = synthetic_data()
        result = editorial.completed_week_comparison(data, "S", date(2026, 10, 11))
        self.assertEqual(result["latest_start"], "2026-10-05")
        self.assertEqual(result["latest_end"], "2026-10-11")
        self.assertEqual(result["latest_gap"], 10.0)
        self.assertEqual(result["previous_gap"], 15.0)
        self.assertEqual(result["change"], -5.0)
        self.assertEqual(
            editorial.completed_week_comparison(data, "G", date(2026, 10, 14)),
            result,
        )

    def test_incomplete_week_is_not_published(self):
        data = synthetic_data(omit=(date(2026, 10, 10),))
        self.assertIsNone(editorial.completed_week_comparison(data, "G", date(2026, 10, 11)))

    def test_no_changes_to_input_price_series(self):
        data = synthetic_data()
        before = repr(data)
        editorial.completed_annual_gaps(data, "S", 2027, BOUCLIER)
        editorial.completed_week_comparison(data, "S", date(2026, 10, 11))
        self.assertEqual(repr(data), before)


if __name__ == "__main__":
    unittest.main()
