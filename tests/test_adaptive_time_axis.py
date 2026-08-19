from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "freshness.js").read_text(encoding="utf-8")

class AdaptiveTimeAxisTests(unittest.TestCase):
    def test_short_windows_get_bimonthly_markers(self):
        self.assertIn("spanMonths<=15?2:spanMonths<=30?3:12", JS)

    def test_both_charts_receive_adaptive_callback(self):
        self.assertIn("chart.options.scales.x.ticks.callback=c1AdaptiveTickLabel", JS)
        self.assertIn("[chartPrix,chartEcart]", JS)

if __name__ == "__main__":
    unittest.main()
