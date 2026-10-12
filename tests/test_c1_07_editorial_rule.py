from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "editorial-patch.js"


class C107EditorialRuleTests(unittest.TestCase):
    def test_old_15_cent_wording_is_gone(self):
        text = PATCH.read_text(encoding="utf-8")
        self.assertNotIn("à moins de 1,5", text)

    def test_detector_rules_stay_technical_not_public_editorial(self):
        text = PATCH.read_text(encoding="utf-8")
        detector = (ROOT / "scripts" / "bouclier_detector.py").read_text(encoding="utf-8")
        self.assertIn("current_active", text)
        self.assertNotIn("latest_at_cap_share", text)
        self.assertNotIn("latest_total_stations", text)
        self.assertNotIn("75e percentile des stations corses non", text)
        self.assertIn("CAP_BELOW_TOLERANCE_EUR = 0.002", detector)
        self.assertIn("CAP_ABOVE_TOLERANCE_EUR = 0.001", detector)


if __name__ == "__main__":
    unittest.main()
