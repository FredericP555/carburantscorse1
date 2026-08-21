#!/usr/bin/env python3
"""Prepared (inactive) A4C reliability policy.

This module encodes the proposed post-Monday rule without activating it in any
publication pipeline.

Principles
----------
* Normal rule: 45 calendar days per station x fuel.
  A declaration on J0 is usable on J0..J+44; at J+45 it is stale.
* A same-price redeclaration resets the clock because the clock is based on the
  declaration timestamp, not on a visible price change.
* Mainland after J+45: a recent declaration of any other fuel can prove station
  liveness and temporarily preserve the target price, but never once the target
  price reaches age 90 days. The liveness declaration itself must be normally
  fresh (<45 days). This rule is independent of brand/shield identification.
* Corsica shield exceptions apply only to TotalEnergies, only when the shield
  status has already been established from normally-fresh observations, and
  only when the last price is at the applicable cap.
* Corsica liveness under the shield: use the other principal fuel
  (Gazole <-> SP95).
* Double cap in Corsica: if Gazole and SP95 are both at their effective caps,
  Rotterdam may suspend the 45-day expiry for both fuels while the Gazole cap
  remains economically constraining.
* Rotterdam does not prove the SP95 market price; it is used only in the
  explicit double-cap hypothesis.
* Independent inactivity, target-fuel rupture, or an invalid latest price
  always overrides every exception.
* A Corsica shield must never resurrect a value that was already stale when
  the relevant cap phase began. ``eligible_at_cap_entry`` enforces that guard.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

NORMAL_MAX_AGE_DAYS = 45
MAINLAND_ABSOLUTE_MAX_AGE_DAYS = 90
CAP_TOLERANCE_BELOW_EUR = 0.002
CAP_TOLERANCE_ABOVE_EUR = 0.001
PRINCIPAL_FUELS = frozenset({"Gazole", "SP95"})


@dataclass(frozen=True)
class Decision:
    eligible: bool
    reason: str
    age_days: int | None


def age_days(last_declared_at: datetime | None, day: date) -> int | None:
    if last_declared_at is None:
        return None
    return (day - last_declared_at.date()).days


def normally_fresh(last_declared_at: datetime | None, day: date) -> bool:
    age = age_days(last_declared_at, day)
    return age is not None and 0 <= age < NORMAL_MAX_AGE_DAYS


def at_cap(price: float | None, cap: float | None) -> bool:
    if price is None or cap is None:
        return False
    return (cap - CAP_TOLERANCE_BELOW_EUR) <= float(price) <= (cap + CAP_TOLERANCE_ABOVE_EUR)


def recent_liveness(*, region_kind: str, target_fuel: str, activity_by_fuel: Mapping[str, datetime], day: date) -> bool:
    """Whether another normally-fresh declaration proves recent station activity."""
    if region_kind not in {"corsica", "mainland"}:
        raise ValueError("region_kind must be 'corsica' or 'mainland'")
    for fuel, ts in activity_by_fuel.items():
        if fuel == target_fuel:
            continue
        if region_kind == "corsica" and fuel not in PRINCIPAL_FUELS:
            continue
        if normally_fresh(ts, day):
            return True
    return False


def evaluate(*, day: date, region_kind: str, target_fuel: str,
             last_declared_at: datetime | None, last_price: float | None,
             latest_price_valid: bool = True, target_rupture_active: bool = False,
             independently_inactive: bool = False, is_total: bool = False,
             shield_effective: bool = False, applicable_cap: float | None = None,
             eligible_at_cap_entry: bool = False,
             activity_by_fuel: Mapping[str, datetime] | None = None,
             gazole_price: float | None = None, gazole_cap: float | None = None,
             sp95_price: float | None = None, sp95_cap: float | None = None,
             rotterdam_gazole_constraining: bool | None = None) -> Decision:
    """Evaluate one station/fuel/day under the prepared policy."""
    age = age_days(last_declared_at, day)
    if independently_inactive:
        return Decision(False, "inactive_independant", age)
    if target_rupture_active:
        return Decision(False, "rupture_active", age)
    if last_declared_at is None or last_price is None or not latest_price_valid:
        return Decision(False, "prix_absent_ou_invalide", age)
    if normally_fresh(last_declared_at, day):
        return Decision(True, "normal_45j", age)

    activity_by_fuel = activity_by_fuel or {}

    # Mainland rule: after the normal 45-day window, recent activity on any
    # other declared fuel can support the old target price, but only up to J+89.
    # J+90 is an absolute stop even if another fuel was declared today.
    if region_kind == "mainland":
        if age is None or age >= MAINLAND_ABSOLUTE_MAX_AGE_DAYS:
            return Decision(False, "continent_age_absolu_90j", age)
        if recent_liveness(
            region_kind=region_kind,
            target_fuel=target_fuel,
            activity_by_fuel=activity_by_fuel,
            day=day,
        ):
            return Decision(True, "continent_vivacite_bornee", age)
        return Decision(False, "continent_sans_vivacite_recente", age)

    # Corsica: beyond 45 days the prepared exception is limited to an effective
    # TotalEnergies shield and keeps all the cap-entry guards.
    if not (is_total and shield_effective):
        return Decision(False, "ancien_hors_exception", age)
    if not eligible_at_cap_entry:
        return Decision(False, "pas_de_resurrection_a_entree_plafond", age)
    if not at_cap(last_price, applicable_cap):
        return Decision(False, "ancien_pas_au_plafond", age)
    if recent_liveness(
        region_kind=region_kind,
        target_fuel=target_fuel,
        activity_by_fuel=activity_by_fuel,
        day=day,
    ):
        return Decision(True, "bouclier_vivacite_croisee", age)
    both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
    if both_capped and rotterdam_gazole_constraining is True:
        return Decision(True, "bouclier_double_plafond_rotterdam", age)
    return Decision(False, "bouclier_sans_preuve_vivacite", age)
