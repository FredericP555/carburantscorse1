#!/usr/bin/env python3
import unittest
from datetime import date, timedelta

import bouclier_detector as bd


class BouclierRuleTests(unittest.TestCase):
    def setUp(self):
        self.d = date(2026, 7, 1)

    def stable(self, flags):
        items=[(self.d+timedelta(days=i), value) for i,value in enumerate(flags)]
        return [value for _day,value in bd._stable_flags(items)]

    def test_single_day_is_not_confirmed(self):
        self.assertEqual(self.stable([False, True, False]), [False, False, False])

    def test_two_consecutive_days_are_confirmed_from_first_day(self):
        self.assertEqual(self.stable([False, True, True, False]), [False, True, True, False])

    def test_one_day_gap_between_confirmed_runs_is_filled(self):
        self.assertEqual(self.stable([True, True, False, True, True]), [True, True, True, True, True])

    def test_two_singletons_do_not_create_a_false_period(self):
        self.assertEqual(self.stable([True, False, True]), [False, False, False])

    def test_rule_constants_match_published_method(self):
        self.assertEqual(bd.CAP_BELOW_TOLERANCE_EUR, 0.002)
        self.assertEqual(bd.CAP_ABOVE_TOLERANCE_EUR, 0.001)
        self.assertEqual(bd.MIN_TOTAL_AT_CAP_COUNT, 1)
        self.assertEqual(bd.CONFIRMATION_DAYS, 2)
        self.assertEqual(bd.MAX_GAP_DAYS, 1)
        self.assertEqual(bd.MARKET_QUANTILE, 0.75)


if __name__ == '__main__':
    unittest.main()
