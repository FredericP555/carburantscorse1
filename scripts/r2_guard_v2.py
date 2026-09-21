#!/usr/bin/env python3
"""Corsica UFIP/R2 guards for prolonged TotalEnergies shield prices.\n\nThe legacy stale_price_admissible helper is retained for compatibility. Production\nuses corsica_shield_price_admissible for the per-fuel Total Corsica exception.\n"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

import rotterdam_corse_shared_v2 as rotterdam
import shield_phase_v2 as shield_phase

NORMAL_MAX_AGE_DAYS = 45


def corsica_shield_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    fuel: str,
    *,
    bouclier_metadata: Mapping,
    observed_file: str | Path = rotterdam.OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DAILY_FILE,
) -> bool:
    """Return whether an old Total cap price may continue for one Corsica fuel.

    The price must belong to the effective cap phase covering the target day. A declaration
    before the phase is monitored from phase start; one made during the phase is monitored
    from its declaration day. Any UFIP/R2 breach blocks continued carry until a later
    declaration resets the evidence window.
    """
    if last_declared_at is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day:
        return False
    phase = shield_phase.phase_for_day(bouclier_metadata, fuel, day)
    if phase is None:
        return False
    start_day = max(declared_on, phase.started_on)
    return rotterdam.admissible_since(
        start_day,
        day,
        phase_started_on=phase.started_on,
        observed_file=observed_file,
        daily_file=daily_file,
    )



def stale_price_admissible(last_declared_at: datetime | None, day: date, *, bouclier_metadata: Mapping,
                           observed_file: str | Path = rotterdam.OBSERVED_FILE,
                           daily_file: str | Path = rotterdam.DAILY_FILE) -> bool:
    if last_declared_at is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day:
        return False
    period = shield_phase.double_cap_period_for_day(bouclier_metadata, day)
    if period is None:
        return False
    stale_start = declared_on + timedelta(days=NORMAL_MAX_AGE_DAYS)
    if day < stale_start:
        return True
    if stale_start < period.started_on:
        return False
    return rotterdam.admissible_since(stale_start, day, phase_started_on=period.started_on,
                                      observed_file=observed_file, daily_file=daily_file)
