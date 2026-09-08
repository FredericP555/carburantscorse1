from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "editorial-patch.js"


class C107EditorialRuleTests(unittest.TestCase):
    def test_old_15_cent_wording_is_gone(self):
        text = PATCH.read_text(encoding="utf-8")
        self.assertNotIn("à moins de 1,5", text)

    def test_editorial_wording_matches_detector_band(self):
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn("de 0,2 c/L sous à 0,1 c/L au-dessus", text)
        self.assertIn("latest_at_cap_share", text)
        self.assertIn("75e percentile des stations corses non‑Total", text)


if __name__ == "__main__":
    unittest.main()
