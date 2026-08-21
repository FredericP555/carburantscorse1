from datetime import date, datetime
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reliability_policy_v2 as p

D = date(2026, 8, 19)


class T(unittest.TestCase):
    def ev(self, **k):
        args = dict(
            day=D,
            region_kind='corsica',
            target_fuel='SP95',
            last_declared_at=datetime(2026, 3, 1),
            last_price=1.99,
        )
        args.update(k)
        return p.evaluate(**args)

    def shield_args(self, **extra):
        args = dict(
            is_total=True,
            shield_effective=True,
            applicable_cap=1.99,
            phase_started_on=date(2026, 3, 20),
        )
        args.update(extra)
        return args

    def test_45(self):
        self.assertTrue(self.ev(last_declared_at=datetime(2026, 7, 6)).eligible)
        self.assertFalse(self.ev(last_declared_at=datetime(2026, 7, 5)).eligible)

    def test_corse_single_cap_cross_liveness_renews_45_days(self):
        d = self.ev(**self.shield_args(activity_by_fuel={'Gazole': datetime(2026, 8, 10)}))
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'bouclier_vivacite_croisee_45j')

    def test_corse_single_cap_cross_liveness_expires_after_45_days(self):
        d = self.ev(**self.shield_args(activity_by_fuel={'Gazole': datetime(2026, 7, 5)}))
        self.assertFalse(d.eligible)

    def test_mainland_any_fuel_extends_after_45(self):
        d = self.ev(
            region_kind='mainland',
            last_declared_at=datetime(2026, 6, 20),
            activity_by_fuel={'E10': datetime(2026, 8, 18)},
        )
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'continent_vivacite_bornee')

    def test_mainland_age_89_can_still_use_liveness(self):
        self.assertTrue(self.ev(
            region_kind='mainland',
            last_declared_at=datetime(2026, 5, 22),
            activity_by_fuel={'E10': datetime(2026, 8, 18)},
        ).eligible)

    def test_mainland_age_90_is_absolute_stop(self):
        d = self.ev(
            region_kind='mainland',
            last_declared_at=datetime(2026, 5, 21),
            activity_by_fuel={'E10': datetime(2026, 8, 18)},
        )
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'continent_age_absolu_90j')

    def test_stale_e10_cannot_use_exception(self):
        d = self.ev(
            region_kind='mainland',
            target_fuel='E10',
            last_declared_at=datetime(2026, 6, 20),
            last_price=1.80,
            activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
        )
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'exception_carburant_non_principal')

    def test_corse_e10_does_not_prove_single_cap_liveness(self):
        d = self.ev(**self.shield_args(activity_by_fuel={'E10': datetime(2026, 8, 18)}))
        self.assertFalse(d.eligible)

    def test_double_cap_uses_rotterdam_not_cross_liveness(self):
        args = self.shield_args(
            activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_gazole_constraining=False,
        )
        d = self.ev(**args)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_sous_r2')

    def test_double_cap_rotterdam_admissible(self):
        d = self.ev(**self.shield_args(
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_gazole_constraining=True,
        ))
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_admissible')

    def test_no_resurrection_when_stale_at_phase_entry(self):
        d = self.ev(**self.shield_args(
            phase_started_on=date(2026, 5, 1),
            activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
        ))
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'pas_de_resurrection_a_entree_plafond')

    def test_target_redeclaration_inside_phase_restores_phase_eligibility(self):
        self.assertTrue(p.declaration_eligible_for_phase(
            datetime(2026, 5, 10), date(2026, 5, 1)
        ))

    def test_new_cap_phase_rechecks_old_price(self):
        self.assertTrue(p.declaration_eligible_for_phase(
            datetime(2026, 4, 1), date(2026, 4, 8)
        ))
        self.assertFalse(p.declaration_eligible_for_phase(
            datetime(2026, 2, 1), date(2026, 4, 8)
        ))

    def test_inactive_overrides(self):
        d = self.ev(**self.shield_args(
            independently_inactive=True,
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_gazole_constraining=True,
        ))
        self.assertFalse(d.eligible)

    def test_non_finite_price_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 18), last_price=math.nan)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')

    def test_future_target_declaration_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 20), last_price=1.99)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')


if __name__ == '__main__':
    unittest.main()
