from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from a4c_common.ufip import validate_ufip_source_contract
from scripts.resolve_corse_station_brands_incremental import ids_to_fetch, resolve_incremental
from scripts.ufip_retry_policy import should_retry_week


class TemporalCorsicaBrandTests(unittest.TestCase):
    def test_stale_known_brand_is_targeted_for_reverification(self):
        stations = {
            "20000001": {
                "enseigne": "VITO",
                "segment": "traditionnel",
                "active": True,
                "verified_at": "2026-01-01T00:00:00+00:00",
            }
        }
        self.assertEqual(
            ids_to_fetch({"20000001"}, stations, today=date(2026, 9, 8), reverify_days=90, limit=12),
            ["20000001"],
        )

    def test_fresh_known_brand_is_not_refetched(self):
        stations = {
            "20000001": {
                "enseigne": "VITO",
                "segment": "traditionnel",
                "active": True,
                "verified_at": "2026-09-01T00:00:00+00:00",
            }
        }
        self.assertEqual(
            ids_to_fetch({"20000001"}, stations, today=date(2026, 9, 8), reverify_days=90, limit=12),
            [],
        )

    def test_returning_station_is_reverified_and_brand_change_is_temporal(self):
        registry = {
            "schema": "a4c-corsica-station-brands-v2",
            "stations": {
                "20000001": {
                    "enseigne": "VITO",
                    "segment": "traditionnel",
                    "detail": "marque_tradi",
                    "classification_source": "auto",
                    "brand_source": "officiel",
                    "active": False,
                    "first_seen": "2026-01-01",
                    "last_seen": "2026-08-01",
                    "verified_at": "2026-08-01T00:00:00+00:00",
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            corrections = Path(tmp) / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")
            updated, summary = resolve_incremental(
                registry,
                {"20000001"},
                corrections,
                fetcher=lambda _sid: ("TotalEnergies", None),
                today=date(2026, 9, 8),
                now=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
            )
        entry = updated["stations"]["20000001"]
        self.assertEqual(summary["brand_fetch_count"], 1)
        self.assertEqual(entry["enseigne"], "TotalEnergies")
        self.assertEqual(entry["brand_valid_from"], "2026-09-08")
        self.assertEqual(entry["brand_history"][-1]["enseigne"], "VITO")
        self.assertEqual(entry["brand_history"][-1]["valid_to"], "2026-09-07")


class UfipContractTests(unittest.TestCase):
    def test_source_contract_requires_eur_per_litre_and_5_day_moving_average(self):
        html = "Cotations Rotterdam (€ /litre) Source : Thomson-Reuters (moyennes mobiles sur 5 jours)"
        validate_ufip_source_contract(html)
        with self.assertRaises(RuntimeError):
            validate_ufip_source_contract("Cotations Rotterdam (€ /tonne) Source : Thomson-Reuters")
        with self.assertRaises(RuntimeError):
            validate_ufip_source_contract("Cotations Rotterdam (€ /litre) Source : Thomson-Reuters")

    def test_retry_detects_same_date_value_correction(self):
        week = date(2026, 8, 31)
        baseline = pd.DataFrame({
            "date": ["2026-08-31", "2026-09-01", "2026-09-03", "2026-09-04"],
            "rotterdam_eur_l": [0.70, 0.71, 0.72, 0.73],
        })
        live = baseline.copy()
        live.loc[live["date"] == "2026-09-03", "rotterdam_eur_l"] = 0.725
        decision = should_retry_week(baseline, live, week)
        self.assertTrue(decision["ready"])
        self.assertEqual(decision["reason"], "complete_week_values_changed")

    def test_retry_ignores_identical_complete_week(self):
        week = date(2026, 8, 31)
        baseline = pd.DataFrame({
            "date": ["2026-08-31", "2026-09-01", "2026-09-03", "2026-09-04"],
            "rotterdam_eur_l": [0.70, 0.71, 0.72, 0.73],
        })
        decision = should_retry_week(baseline, baseline.copy(), week)
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["reason"], "already_current")

    def test_retry_still_detects_late_completion(self):
        week = date(2026, 8, 31)
        baseline = pd.DataFrame({
            "date": ["2026-08-31", "2026-09-01"],
            "rotterdam_eur_l": [0.70, 0.71],
        })
        live = pd.DataFrame({
            "date": ["2026-08-31", "2026-09-01", "2026-09-03", "2026-09-04"],
            "rotterdam_eur_l": [0.70, 0.71, 0.72, 0.73],
        })
        decision = should_retry_week(baseline, live, week)
        self.assertTrue(decision["ready"])
        self.assertEqual(decision["reason"], "week_became_complete")


class PublicMethodTextTests(unittest.TestCase):
    def test_frontend_uses_bouclier_rule_metadata_not_obsolete_15_cent_label(self):
        text = (Path(__file__).resolve().parents[1] / "automation.js").read_text(encoding="utf-8")
        self.assertIn("cap_tolerance_below_cents", text)
        self.assertIn("cap_tolerance_above_cents", text)
        self.assertNotIn("à moins de 1,5 c€/L", text)


if __name__ == "__main__":
    unittest.main()
