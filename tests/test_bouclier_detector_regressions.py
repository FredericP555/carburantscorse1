from datetime import date as RealDate, datetime
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bouclier_detector as b


class FakeDate(RealDate):
    @classmethod
    def today(cls):
        return cls(2026, 1, 7)


class BouclierDetectorRegressionT(unittest.TestCase):
    def test_cap_plus_one_millieuro_is_at_cap(self):
        self.assertTrue(b.price_at_cap(1.991, 1.99))
        self.assertTrue(b.price_at_cap(2.091, 2.09))
        self.assertTrue(b.price_at_cap(2.251, 2.25))

    def test_missing_population_day_is_explicit_false_and_bridgeable(self):
        # SP95 is active 1-2 Jan, Total reports an unusable None on 3 Jan,
        # then becomes active again 4-6 Jan.  The 3 Jan must exist as False so
        # the one-day gap rule can bridge it into one confirmed range.
        source = {
            ('T', 'corse', 'SP95'): [
                (datetime(2026, 1, 1, 8), 1.991),
                (datetime(2026, 1, 3, 8), None),
                (datetime(2026, 1, 4, 8), 1.99),
            ],
            ('N', 'corse', 'SP95'): [
                (datetime(2026, 1, 1, 8), 2.00),
            ],
        }

        def fake_parse_year(year):
            return source if year == 2026 else {}

        def fake_brand(station_id):
            return b.BRAND_TOTAL if station_id == 'T' else b.BRAND_NON_TOTAL

        with mock.patch.object(b, 'date', FakeDate), \
             mock.patch.object(b.core, 'parse_year', fake_parse_year), \
             mock.patch.object(b, '_brand_state', fake_brand):
            result = b.detect_year(2026)['SP95']

        self.assertIn(RealDate(2026, 1, 3), result['flags'])
        self.assertTrue(result['flags'][RealDate(2026, 1, 3)])
        self.assertEqual(
            result['detected_ranges'],
            [(RealDate(2026, 1, 1), RealDate(2026, 1, 6))],
        )
        self.assertEqual(result['stats'][RealDate(2026, 1, 1)]['at_cap_count'], 1)


if __name__ == '__main__':
    unittest.main()
