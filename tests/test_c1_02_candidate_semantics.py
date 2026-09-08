from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import unittest

import c1_candidate_semantics as semantics
import update_data_v2 as core


def _daily(off: int, ttc: float, vat: float) -> list:
    return [off, round(ttc, 3), round(ttc / vat, 3)]


def _series(short: str, region: str, through: int) -> dict:
    ttc = 1.80 if short == "G" else 1.90
    vat = 1.13 if region == "corse" else 1.20
    daily = [_daily(off, ttc, vat) for off in range(through + 1)]
    weekly = []
    monthly = []
    seen_w = set()
    seen_m = set()
    for off in range(through + 1):
        day = core.ORIGIN + timedelta(days=off)
        monday = day - timedelta(days=day.weekday())
        wk = (monday - core.ORIGIN).days
        mk = f"{day.year:04d}-{day.month:02d}"
        if wk not in seen_w:
            weekly.append([wk, round(ttc, 3), round(ttc / vat, 3)])
            seen_w.add(wk)
        if mk not in seen_m:
            monthly.append([mk, round(ttc, 3), round(ttc / vat, 3)])
            seen_m.add(mk)
    return {"d": daily, "w": weekly, "m": monthly}


def _payload(through: int) -> dict:
    last_date = str(core.ORIGIN + timedelta(days=through))
    return {
        "G": {"corse": _series("G", "corse", through)},
        "S": {"corse": _series("S", "corse", through)},
        "meta": {"last_date": last_date},
    }


class C1AggregateSemanticTests(unittest.TestCase):
    def setUp(self):
        self.baseline = _payload(8)
        self.candidate = _payload(9)
        self.first_new_day = core.ORIGIN + timedelta(days=9)

    def test_valid_mutable_week_and_month_pass(self):
        semantics.validate_mutable_aggregates(
            self.baseline, self.candidate, self.first_new_day
        )

    def test_rejects_corrupted_mutable_week(self):
        bad = deepcopy(self.candidate)
        bad["G"]["corse"]["w"][-1][1] = 99.0
        with self.assertRaises(ValueError):
            semantics.validate_mutable_aggregates(
                self.baseline, bad, self.first_new_day
            )

    def test_rejects_corrupted_mutable_month(self):
        bad = deepcopy(self.candidate)
        bad["S"]["corse"]["m"][-1][1] = 99.0
        with self.assertRaises(ValueError):
            semantics.validate_mutable_aggregates(
                self.baseline, bad, self.first_new_day
            )


class C1SummaryCutoffTests(unittest.TestCase):
    def test_summary_must_end_on_candidate_last_date(self):
        candidate = _payload(9)
        last_date = candidate["meta"]["last_date"]
        good = {"target_end": last_date, "engine": {"source_max_date": last_date}}
        semantics.validate_summary_cutoff(candidate, good)

        stale = {
            "target_end": str(core.ORIGIN + timedelta(days=8)),
            "engine": {"source_max_date": str(core.ORIGIN + timedelta(days=8))},
        }
        with self.assertRaises(ValueError):
            semantics.validate_summary_cutoff(candidate, stale)

    def test_source_cannot_precede_published_cutoff(self):
        candidate = _payload(9)
        bad = {
            "target_end": candidate["meta"]["last_date"],
            "engine": {"source_max_date": str(core.ORIGIN + timedelta(days=8))},
        }
        with self.assertRaises(ValueError):
            semantics.validate_summary_cutoff(candidate, bad)


if __name__ == "__main__":
    unittest.main()
