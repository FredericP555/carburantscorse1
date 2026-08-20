from datetime import date, datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import update_data_v2 as core


class StationActivityPolicyTests(unittest.TestCase):
    def test_old_unchanged_price_remains_eligible_while_station_is_active(self):
        day = date(2026, 8, 19)
        price_ts = datetime(2026, 3, 10, 12, 0)
        station_activity = datetime(2026, 8, 10, 9, 0)

        self.assertGreater((day - price_ts.date()).days, core.MAX_STATION_INACTIVE_DAYS)
        self.assertTrue(core.fuel_value_eligible(price_ts, 1.99, station_activity, [], day))

    def test_station_activity_threshold_is_inclusive_at_45_days(self):
        day = date(2026, 8, 19)
        self.assertTrue(core.station_active(datetime(2026, 7, 5, 12, 0), day))
        self.assertFalse(core.station_active(datetime(2026, 7, 4, 12, 0), day))

    def test_inactive_station_excludes_even_recent_last_fuel_price(self):
        day = date(2026, 8, 19)
        price_ts = datetime(2026, 7, 10, 12, 0)
        station_activity = datetime(2026, 7, 4, 12, 0)

        self.assertFalse(core.fuel_value_eligible(price_ts, 1.99, station_activity, [], day))

    def test_active_rupture_excludes_fuel_without_destroying_last_price(self):
        day = date(2026, 8, 19)
        price_ts = datetime(2026, 3, 10, 12, 0)
        station_activity = datetime(2026, 8, 18, 9, 0)
        open_rupture = [(datetime(2026, 8, 15, 8, 0), None)]

        self.assertFalse(
            core.fuel_value_eligible(price_ts, 1.99, station_activity, open_rupture, day)
        )

    def test_closed_rupture_allows_previous_unchanged_price_to_resume(self):
        day = date(2026, 8, 19)
        price_ts = datetime(2026, 3, 10, 12, 0)
        station_activity = datetime(2026, 8, 18, 9, 0)
        closed_rupture = [
            (datetime(2026, 8, 15, 8, 0), datetime(2026, 8, 18, 11, 0))
        ]

        self.assertTrue(
            core.fuel_value_eligible(price_ts, 1.99, station_activity, closed_rupture, day)
        )

    def test_invalid_latest_price_is_excluded(self):
        day = date(2026, 8, 19)
        self.assertFalse(
            core.fuel_value_eligible(
                datetime(2026, 8, 18, 12, 0),
                None,
                datetime(2026, 8, 18, 12, 0),
                [],
                day,
            )
        )


if __name__ == "__main__":
    unittest.main()
