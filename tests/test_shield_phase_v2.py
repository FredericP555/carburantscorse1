from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import shield_phase_v2 as s


class ShieldPhaseT(unittest.TestCase):
    def test_gazole_range_splits_on_2026_cap_change(self):
        meta = {
            'Gazole': {
                'ranges': [{'d1': '2026-03-20', 'd2': '2026-04-10'}]
            },
            'SP95': {'ranges': []},
        }
        phases = s.phases_from_bouclier_metadata(meta)['Gazole']
        self.assertEqual(
            [(p.started_on, p.ended_on, p.cap) for p in phases],
            [
                (date(2026, 3, 20), date(2026, 4, 7), 2.09),
                (date(2026, 4, 8), date(2026, 4, 10), 2.25),
            ],
        )

    def test_phase_lookup_returns_none_outside_effective_shield(self):
        meta = {
            'Gazole': {'ranges': [{'d1': '2026-04-08', 'd2': '2026-04-10'}]},
            'SP95': {'ranges': []},
        }
        self.assertIsNone(s.phase_for_day(meta, 'Gazole', date(2026, 4, 11)))

    def test_json_metadata_contains_explicit_phase_start(self):
        meta = {
            'Gazole': {'ranges': [{'d1': '2026-04-08', 'd2': '2026-04-10'}]},
            'SP95': {'ranges': []},
        }
        out = s.with_cap_phases(meta)
        phase = out['Gazole']['phases'][0]
        self.assertEqual(phase['d1'], '2026-04-08')
        self.assertEqual(phase['cap'], 2.25)
        self.assertTrue(phase['phase_id'].startswith('Gazole:2026-04-08:'))


if __name__ == '__main__':
    unittest.main()
