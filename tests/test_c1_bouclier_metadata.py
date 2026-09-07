"""Regression tests for C1 publication of dynamic TotalEnergies bouclier metadata."""

import unittest
from pathlib import Path

from scripts import c1_bouclier_meta


def sample_bouclier(end="2026-09-06"):
    return {
        "Gazole": {
            "ranges": [{"d1": "2026-07-23", "d2": end}],
            "current_active": True,
        },
        "SP95": {
            "ranges": [{"d1": "2026-03-12", "d2": end}],
            "current_active": True,
        },
    }


class C1BouclierMetadataTests(unittest.TestCase):
    def test_attach_replaces_stale_value_and_preserves_other_meta(self):
        fresh = sample_bouclier()
        baseline = {
            "v2": {"active": True},
            "other": "keep-me",
            "bouclier": sample_bouclier("2026-08-30"),
        }
        out = c1_bouclier_meta.attach_detector_bouclier(baseline, fresh)
        self.assertEqual(out["bouclier"], fresh)
        self.assertEqual(out["other"], "keep-me")
        self.assertEqual(out["v2"], {"active": True})

    def test_attach_deep_copies_detector_output(self):
        fresh = sample_bouclier()
        out = c1_bouclier_meta.attach_detector_bouclier({}, fresh)
        fresh["Gazole"]["ranges"][0]["d2"] = "2099-01-01"
        self.assertEqual(out["bouclier"]["Gazole"]["ranges"][0]["d2"], "2026-09-06")

    def test_validate_accepts_exact_detector_output(self):
        fresh = sample_bouclier()
        published = c1_bouclier_meta.validate_detector_bouclier(
            {"bouclier": fresh}, fresh
        )
        self.assertEqual(published, fresh)

    def test_validate_rejects_missing_published_metadata(self):
        with self.assertRaisesRegex(ValueError, "published bouclier metadata absent"):
            c1_bouclier_meta.validate_detector_bouclier({}, sample_bouclier())

    def test_validate_rejects_malformed_fuel_ranges(self):
        broken = sample_bouclier()
        broken["SP95"]["ranges"] = None
        with self.assertRaisesRegex(ValueError, "detector bouclier ranges invalid for SP95"):
            c1_bouclier_meta.attach_detector_bouclier({}, broken)

    def test_validate_rejects_stale_published_metadata(self):
        detector = sample_bouclier()
        stale = sample_bouclier("2026-08-30")
        with self.assertRaisesRegex(ValueError, "differs from detector output"):
            c1_bouclier_meta.validate_detector_bouclier(
                {"bouclier": stale}, detector
            )

    def test_builder_and_promoter_are_wired_to_guard(self):
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts/build_c1_v2_candidate.py").read_text(encoding="utf-8")
        promoter = (root / "scripts/promote_c1_v2_candidate.py").read_text(encoding="utf-8")
        self.assertIn("c1_bouclier_meta.attach_detector_bouclier", builder)
        self.assertIn("c1_bouclier_meta.validate_detector_bouclier", promoter)


if __name__ == "__main__":
    unittest.main()
