from datetime import date, datetime
import math
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reliability_policy_v2 as p
D=date(2026,8,19)

class T(unittest.TestCase):
 def ev(self, **k):
  a=dict(day=D,region_kind='corsica',target_fuel='SP95',last_declared_at=datetime(2026,3,1),last_price=1.99)
  a.update(k); return p.evaluate(**a)
 def test_45(self):
  self.assertTrue(self.ev(last_declared_at=datetime(2026,7,6)).eligible)
  self.assertFalse(self.ev(last_declared_at=datetime(2026,7,5)).eligible)
 def test_corse_cross_liveness(self):
  self.assertTrue(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,activity_by_fuel={'Gazole':datetime(2026,8,10)}).eligible)
 def test_mainland_any_fuel_extends_after_45(self):
  d=self.ev(region_kind='mainland',last_declared_at=datetime(2026,6,20),activity_by_fuel={'E10':datetime(2026,8,18)})
  self.assertTrue(d.eligible)
  self.assertEqual(d.reason,'continent_vivacite_bornee')
 def test_mainland_age_89_can_still_use_liveness(self):
  self.assertTrue(self.ev(region_kind='mainland',last_declared_at=datetime(2026,5,22),activity_by_fuel={'E10':datetime(2026,8,18)}).eligible)
 def test_mainland_age_90_is_absolute_stop(self):
  d=self.ev(region_kind='mainland',last_declared_at=datetime(2026,5,21),activity_by_fuel={'E10':datetime(2026,8,18)})
  self.assertFalse(d.eligible)
  self.assertEqual(d.reason,'continent_age_absolu_90j')
 def test_mainland_liveness_itself_must_be_under_45(self):
  self.assertFalse(self.ev(region_kind='mainland',last_declared_at=datetime(2026,6,20),activity_by_fuel={'E10':datetime(2026,7,5)}).eligible)
 def test_stale_e10_cannot_use_exception(self):
  d=self.ev(region_kind='mainland',target_fuel='E10',last_declared_at=datetime(2026,6,20),last_price=1.80,activity_by_fuel={'Gazole':datetime(2026,8,18)})
  self.assertFalse(d.eligible)
  self.assertEqual(d.reason,'exception_carburant_non_principal')
 def test_corse_other_fuel_not_enough(self):
  self.assertFalse(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,activity_by_fuel={'E10':datetime(2026,8,18)}).eligible)
 def test_double_cap_rotterdam(self):
  self.assertTrue(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,gazole_price=2.25,gazole_cap=2.25,sp95_price=1.99,sp95_cap=1.99,rotterdam_gazole_constraining=True).eligible)
 def test_no_resurrection(self):
  self.assertFalse(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=False,activity_by_fuel={'Gazole':datetime(2026,8,18)}).eligible)
 def test_inactive_overrides(self):
  self.assertFalse(self.ev(independently_inactive=True,is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,gazole_price=2.25,gazole_cap=2.25,sp95_price=1.99,sp95_cap=1.99,rotterdam_gazole_constraining=True).eligible)
 def test_non_finite_price_is_rejected(self):
  d=self.ev(last_declared_at=datetime(2026,8,18),last_price=math.nan)
  self.assertFalse(d.eligible)
  self.assertEqual(d.reason,'prix_ou_date_absent_invalide')
 def test_future_target_declaration_is_rejected(self):
  d=self.ev(last_declared_at=datetime(2026,8,20),last_price=1.99)
  self.assertFalse(d.eligible)
  self.assertEqual(d.reason,'prix_ou_date_absent_invalide')

if __name__=='__main__': unittest.main()
