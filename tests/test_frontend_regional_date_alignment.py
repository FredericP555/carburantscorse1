from datetime import date, timedelta
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTO = (ROOT / "automation.js").read_text(encoding="utf-8")
DATA = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
ORIGIN = date(2022, 1, 1)


def day_label(offset):
    return (ORIGIN + timedelta(days=int(offset))).isoformat()


class FrontendRegionalDateAlignmentTests(unittest.TestCase):
    def test_frontend_accessors_are_overridden_by_date_before_window_wrapper(self):
        helper = "function autoAlignedValues(carbuKey, serieName, res, valueIndex)"
        ttc = "getTTC=function(carbuKey,serieName,res)"
        ht = "getHT=function(carbuKey,serieName,res)"
        wrapper = "const _autoBaseBuildPrixDs=buildPrixDs;"

        self.assertIn(helper, AUTO)
        self.assertIn("const byLabel=new Map();", AUTO)
        self.assertIn("return labels.map(label=>byLabel.has(label)?byLabel.get(label):null);", AUTO)
        self.assertIn(ttc, AUTO)
        self.assertIn(ht, AUTO)
        self.assertLess(AUTO.index(ttc), AUTO.index(wrapper))
        self.assertLess(AUTO.index(ht), AUTO.index(wrapper))

    def test_known_sp95_series_align_by_date_not_position(self):
        corse = DATA["S"]["corse"]["d"]
        corse_labels = [day_label(point[0]) for point in corse]

        self.assertTrue(corse_labels)
        self.assertEqual(corse_labels[0], "2022-01-01")

        for region in ("Hauts-de-France", "Normandie"):
            points = DATA["S"][region]["d"]
            by_label = {day_label(point[0]): point[1] for point in points}
            aligned = [by_label.get(label) for label in corse_labels]

            # These two historical series start on 2 January 2022. The old
            # positional frontend incorrectly drew that first value on 1 January.
            self.assertEqual(day_label(points[0][0]), "2022-01-02")
            self.assertIsNone(aligned[0])
            self.assertEqual(aligned[1], points[0][1])

            # The newest regional value must remain attached to its own date.
            last_label = day_label(points[-1][0])
            self.assertEqual(aligned[corse_labels.index(last_label)], points[-1][1])

    def test_alignment_preserves_axis_length_and_internal_gaps(self):
        labels = ["2026-09-01", "2026-09-02", "2026-09-03"]
        values = {"2026-09-01": 1.0, "2026-09-03": 3.0}
        aligned = [values.get(label) for label in labels]
        self.assertEqual(aligned, [1.0, None, 3.0])
        self.assertEqual(len(aligned), len(labels))


if __name__ == "__main__":
    unittest.main()
