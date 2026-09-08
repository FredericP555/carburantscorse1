from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from scripts.ufip_retry_policy import release_contract_current, should_retry_week


CURRENT_ROTTERDAM = {
    "unit": "EUR/L",
    "reference_source": "Thomson-Reuters",
    "smoothing": "5-day moving average",
}


def complete_week() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"],
        "rotterdam_eur_l": [0.892, 0.925, 0.965, 1.0, 1.025],
    })


class UfipReleaseContractRefreshTests(unittest.TestCase):
    def test_current_release_contract_is_accepted(self):
        self.assertTrue(release_contract_current({"rotterdam": dict(CURRENT_ROTTERDAM)}))

    def test_missing_or_wrong_release_contract_is_stale(self):
        self.assertFalse(release_contract_current({}))
        self.assertFalse(release_contract_current({"rotterdam": {}}))
        for field, wrong in (
            ("unit", "EUR/tonne"),
            ("reference_source", "other-source"),
            ("smoothing", "daily spot"),
        ):
            contract = dict(CURRENT_ROTTERDAM)
            contract[field] = wrong
            self.assertFalse(release_contract_current({"rotterdam": contract}), field)

    def test_identical_week_still_retries_when_release_contract_is_outdated(self):
        week = date(2026, 8, 31)
        baseline = complete_week()
        decision = should_retry_week(
            baseline,
            baseline.copy(),
            week,
            release_meta={"rotterdam": {"unit": "EUR/L"}},
        )
        self.assertTrue(decision["ready"])
        self.assertEqual(decision["reason"], "release_contract_outdated")
        self.assertFalse(decision["release_contract_current"])

    def test_identical_week_does_not_retry_when_release_contract_is_current(self):
        week = date(2026, 8, 31)
        baseline = complete_week()
        decision = should_retry_week(
            baseline,
            baseline.copy(),
            week,
            release_meta={"rotterdam": dict(CURRENT_ROTTERDAM)},
        )
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["reason"], "already_current")
        self.assertTrue(decision["release_contract_current"])


if __name__ == "__main__":
    unittest.main()
