"""Regression tests for the C1 V2 event guard used by the production preflight."""

import unittest
from datetime import date, datetime

import build_c1_v2_candidate as candidate


class C1V2EventGuardTests(unittest.TestCase):
    def test_same_start_open_and_explicit_ruptures_are_sortable(self):
        started = datetime(2026, 8, 1, 10, 0)
        events = [
            ("station-1", "rupture", "Gazole", started, None, ""),
            ("station-1", "rupture", "Gazole", started, datetime(2026, 8, 2, 10, 0), ""),
        ]

        guard = candidate.EventGuard(events, {})

        self.assertTrue(guard.rupture_active("station-1", "Gazole", date(2026, 8, 3)))
        self.assertEqual(guard.stats["rupture_open_remaining"], 1)
        self.assertEqual(guard.stats["rupture_explicit_end"], 1)


if __name__ == "__main__":
    unittest.main()
