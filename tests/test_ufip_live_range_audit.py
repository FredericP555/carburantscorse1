from datetime import date
import unittest

from a4c_common.ufip import fetch_rotterdam_gazole


class UfipLiveRangeAudit(unittest.TestCase):
    def test_compare_long_and_short_custom_exports(self):
        windows = {
            "LONG_2026_01_01_TO_2026_10_05": (date(2026, 1, 1), date(2026, 10, 5)),
            "SHORT_2026_09_01_TO_2026_10_05": (date(2026, 9, 1), date(2026, 10, 5)),
        }

        for label, (start, end) in windows.items():
            frame = fetch_rotterdam_gazole(start, end)
            self.assertIn("date", frame.columns)
            self.assertIn("rotterdam_eur_l", frame.columns)

            print(f"AUDIT_UFIP {label} rows={len(frame)}")
            if frame.empty:
                print(f"AUDIT_UFIP {label} max_date=NONE")
                continue

            print(f"AUDIT_UFIP {label} max_date={frame['date'].max()}")
            recent = frame[
                (frame["date"] >= date(2026, 9, 28))
                & (frame["date"] <= date(2026, 10, 2))
            ]
            for row in recent.itertuples(index=False):
                print(
                    f"AUDIT_UFIP {label} "
                    f"{row.date.isoformat()}={float(row.rotterdam_eur_l):.3f}"
                )

        self.fail("AUDIT_COMPLETE_STOP: intentional temporary audit stop")


if __name__ == "__main__":
    unittest.main()
