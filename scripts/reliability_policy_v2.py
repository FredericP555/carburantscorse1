#!/usr/bin/env python3
"""Prepared (inactive) A4C reliability policy.

This module encodes the proposed post-Monday rule without activating it in any
publication pipeline.

Principles
----------
* Normal rule: 45 calendar days per station x fuel. A declaration on J0 is
  usable on J0..J+44; at J+45 it is stale. A same-price redeclaration resets
  the clock because the clock is based on the declaration timestamp.
* Corsica shield exceptions concern only Gazole/SP95 at TotalEnergies stations
  while the independently detected shield is effective.
* With one principal fuel at the cap, a normally-fresh declaration of the other
  principal fuel proves liveness and starts a new rolling 45-day support window.
* With Gazole and SP95 both at their caps, cross-liveness is no longer enough:
  the prepared Corsica rule uses Rotterdam versus R2. R2 affects only whether
  stale station prices remain admissible; it never defines whether the shield
  itself is effective.
* A price already stale when the current cap phase starts cannot be resurrected.
  This is derived from ``phase_started_on`` rather than trusted as a caller
  boolean. A later target-fuel declaration inside the phase is fresh evidence
  and is eligible normally.
* Independent inactivity, target-fuel rupture, invalid/non-finite price or a
  future target declaration always override every exception.
* The separate C1 mainland fallback rule remains bounded at 90 days; that rule
  is not the C2 Bouches-du-Rhone rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Mapping

NORMAL_MAX_AGE_DAYS = 45
MAINLAND_ABSOLUTE_MAX_AGE_DAYS = 90
CAP_TOLERANCE_BELOW_EUR = 0.002
CAP_TOLERANCE_ABOVE_EUR = 0.001
PRINCIPAL_FUELS = frozenset({"Gazole", "SP95"})
VALID_REGION_KINDS = frozenset({"corsica", "mainland"})


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


def finite_number(value: float | None) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def at_cap(price: float | None, cap: float | None) -> bool:
    if not finite_number(price) or not finite_number(cap):
        return False
    price_f = float(price)
    cap_f = float(cap)
    return (cap_f - CAP_TOLERANCE_BELOW_EUR) <= price_f <= (cap_f + CAP_TOLERANCE_ABOVE_EUR)


def recent_liveness(
    *,
    region_kind: str,
    target_fuel: str,
    activity_by_fuel: Mapping[str, datetime],
    day: date,
) -> bool:
    """Whether another fresh declaration supports the target for another 45 days."""
    if region_kind not in VALID_REGION_KINDS:
        raise ValueError("region_kind must be 'corsica' or 'mainland'")
    for fuel, ts in activity_by_fuel.items():
        if fuel == target_fuel:
            continue
        if region_kind == "corsica" and fuel not in PRINCIPAL_FUELS:
            continue
        if normally_fresh(ts, day):
            return True
    return False


def declaration_eligible_for_phase(
    last_declared_at: datetime | None,
    phase_started_on: date | None,
) -> bool:
    """Apply the no-resurrection guard for the current cap phase.

    A declaration is eligible when it was still <45 days old at phase entry, or
    when the target fuel was declared again after the phase started. This means
    a cap change automatically causes a fresh check simply by changing the phase
    start date supplied by the cap/shield phase builder.
    """
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on >= phase_started_on:
        return True
    age_at_entry = (phase_started_on - declared_on).days
    return 0 <= age_at_entry < NORMAL_MAX_AGE_DAYS


def evaluate(
    *,
    day: date,
    region_kind: str,
    target_fuel: str,
    last_declared_at: datetime | None,
    last_price: float | None,
    latest_price_valid: bool = True,
    target_rupture_active: bool = False,
    independently_inactive: bool = False,
    is_total: bool = False,
    shield_effective: bool = False,
    applicable_cap: float | None = None,
    phase_started_on: date | None = None,
    activity_by_fuel: Mapping[str, datetime] | None = None,
    gazole_price: float | None = None,
    gazole_cap: float | None = None,
    sp95_price: float | None = None,
    sp95_cap: float | None = None,
    rotterdam_gazole_constraining: bool | None = None,
) -> Decision:
    """Evaluate one station/fuel/day under the prepared policy."""
    if region_kind not in VALID_REGION_KINDS:
        raise ValueError("region_kind must be 'corsica' or 'mainland'")

    age = age_days(last_declared_at, day)
    if independently_inactive:
        return Decision(False, "inactive_independant", age)
    if target_rupture_active:
        return Decision(False, "rupture_active", age)
    if (
        last_declared_at is None
        or age is None
        or age < 0
        or not latest_price_valid
        or not finite_number(last_price)
    ):
        return Decision(False, "prix_ou_date_absent_invalide", age)
    if normally_fresh(last_declared_at, day):
        return Decision(True, "normal_45j", age)

    if target_fuel not in PRINCIPAL_FUELS:
        return Decision(False, "exception_carburant_non_principal", age)

    activity_by_fuel = activity_by_fuel or {}

    # C1 mainland fallback only. It is intentionally distinct from C2/BdR.
    if region_kind == "mainland":
        if age >= MAINLAND_ABSOLUTE_MAX_AGE_DAYS:
            return Decision(False, "continent_age_absolu_90j", age)
        if recent_liveness(
            region_kind=region_kind,
            target_fuel=target_fuel,
            activity_by_fuel=activity_by_fuel,
            day=day,
        ):
            return Decision(True, "continent_vivacite_bornee", age)
        return Decision(False, "continent_sans_vivacite_recente", age)

    # Corse: the shield status comes from the independent detector. R2 never
    # turns that detector on or off; it only affects stale-price admissibility.
    if not (is_total and shield_effective):
        return Decision(False, "ancien_hors_exception", age)
    if phase_started_on is None or phase_started_on > day:
        return Decision(False, "phase_plafond_absente_ou_invalide", age)
    if not declaration_eligible_for_phase(last_declared_at, phase_started_on):
        return Decision(False, "pas_de_resurrection_a_entree_plafond", age)
    if not at_cap(last_price, applicable_cap):
        return Decision(False, "ancien_pas_au_plafond", age)

    both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
    if both_capped:
        if rotterdam_gazole_constraining is True:
            return Decision(True, "double_plafond_rotterdam_admissible", age)
        if rotterdam_gazole_constraining is False:
            return Decision(False, "double_plafond_rotterdam_sous_r2", age)
        return Decision(False, "double_plafond_rotterdam_indisponible", age)

    if recent_liveness(
        region_kind="corsica",
        target_fuel=target_fuel,
        activity_by_fuel=activity_by_fuel,
        day=day,
    ):
        return Decision(True, "bouclier_vivacite_croisee_45j", age)
    return Decision(False, "bouclier_sans_vivacite_recente", age)
