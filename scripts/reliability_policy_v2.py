#!/usr/bin/env python3
"""Prepared (inactive) A4C reliability policy.

Normal freshness is 45 calendar days per station x fuel. Shield-effective status
is determined independently; R2 only controls stale-price admissibility in the
double-cap case and never starts or ends the shield.
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
    *, region_kind: str, target_fuel: str,
    activity_by_fuel: Mapping[str, datetime], day: date,
) -> bool:
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
    """No-resurrection guard for the current cap phase."""
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on >= phase_started_on:
        return True
    age_at_entry = (phase_started_on - declared_on).days
    return 0 <= age_at_entry < NORMAL_MAX_AGE_DAYS


def evaluate(
    *, day: date, region_kind: str, target_fuel: str,
    last_declared_at: datetime | None, last_price: float | None,
    latest_price_valid: bool = True, target_rupture_active: bool = False,
    independently_inactive: bool = False, is_total: bool = False,
    shield_effective: bool = False, applicable_cap: float | None = None,
    phase_started_on: date | None = None,
    activity_by_fuel: Mapping[str, datetime] | None = None,
    gazole_price: float | None = None, gazole_cap: float | None = None,
    sp95_price: float | None = None, sp95_cap: float | None = None,
    rotterdam_stale_price_admissible: bool | None = None,
) -> Decision:
    if region_kind not in VALID_REGION_KINDS:
        raise ValueError("region_kind must be 'corsica' or 'mainland'")

    age = age_days(last_declared_at, day)
    if independently_inactive:
        return Decision(False, "inactive_independant", age)
    if target_rupture_active:
        return Decision(False, "rupture_active", age)
    if (
        last_declared_at is None or age is None or age < 0
        or not latest_price_valid or not finite_number(last_price)
    ):
        return Decision(False, "prix_ou_date_absent_invalide", age)
    if normally_fresh(last_declared_at, day):
        return Decision(True, "normal_45j", age)

    if target_fuel not in PRINCIPAL_FUELS:
        return Decision(False, "exception_carburant_non_principal", age)

    activity_by_fuel = activity_by_fuel or {}

    # C1 mainland fallback only; deliberately distinct from C2/BdR.
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
        if rotterdam_stale_price_admissible is True:
            return Decision(True, "double_plafond_rotterdam_admissible", age)
        if rotterdam_stale_price_admissible is False:
            return Decision(False, "double_plafond_rotterdam_verrouille", age)
        return Decision(False, "double_plafond_rotterdam_indisponible", age)

    if recent_liveness(
        region_kind="corsica",
        target_fuel=target_fuel,
        activity_by_fuel=activity_by_fuel,
        day=day,
    ):
        return Decision(True, "bouclier_vivacite_croisee_45j", age)
    return Decision(False, "bouclier_sans_vivacite_recente", age)
