from __future__ import annotations

from datetime import date
import inspect
import unittest

from a4c_common.corse_brand import NON_TOTAL_CONFIRMED, TOTAL
from scripts import build_c1_v2_candidate as builder


class C1TemporalBrandConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.entry = {
            "enseigne": "TotalEnergies",
            "segment": "traditionnel",
            "brand_source": "verified",
            "brand_valid_from": "2026-09-08",
            "brand_history": [
                {
                    "enseigne": "VITO",
                    "segment": "traditionnel",
                    "brand_source": "verified",
                    "valid_from": "2026-01-01",
                    "valid_to": "2026-09-07",
                }
            ],
        }

    def test_identity_change_applies_prospectively_by_calculated_day(self):
        self.assertEqual(
            builder._corsica_brand_classification(self.entry, date(2026, 9, 7)),
            NON_TOTAL_CONFIRMED,
        )
        self.assertEqual(
            builder._corsica_brand_classification(self.entry, date(2026, 9, 8)),
            TOTAL,
        )

    def test_builder_resolves_brand_inside_day_loop(self):
        source = inspect.getsource(builder.build_v2_daily)
        self.assertIn("_corsica_brand_classification(brand_entry, day)", source)
        self.assertNotIn("classify_registry_entry(brands.get(sid))", source)

    def test_builder_exposes_population_reconciliation_evidence(self):
        source = inspect.getsource(builder.build_v2_daily)
        self.assertIn('"brand_population_reconciliation"', source)
        self.assertIn('"classification_is_date_aware": True', source)
        self.assertIn('"v2_latest_eligible_population"', source)
        self.assertIn('"detector_latest_population"', source)
        self.assertIn("legacy_station_audit_scope", source)


if __name__ == "__main__":
    unittest.main()
