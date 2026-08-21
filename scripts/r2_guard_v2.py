#!/usr/bin/env python3
"""Prepared Corsica R2 guard derived from declaration + current shield phase."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import rotterdam_corse_shared_v2 as rotterdam

NORMAL_MAX_AGE_DAYS = 45


def stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    *,
    phase_started_on: date | None,
    observed_file: str | Path = rotterdam.OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DAILY_FILE,
) -> bool:
    """Return the persistent phase-specific R2 verdict.

    J0..J+44 do not need the R2 exception. From J+45, Rotterdam is checked
    against the R2 calibrated for the current effective-shield cap phase.
    A new target declaration moves J+45; a later shield-effective restart moves
    ``phase_started_on`` and therefore computes a new R1/R2 from the quotations
    immediately preceding that new phase.
    """
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day or phase_started_on > day:
        return False
    stale_start = declared_on + timedelta(days=NORMAL_MAX_AGE_DAYS)
    if day < stale_start:
        return True
    # A target already stale when the phase starts is rejected separately by the
    # no-resurrection guard. Fail closed here too if this helper is called alone.
    if stale_start < phase_started_on:
        return False
    return rotterdam.admissible_since(
        stale_start,
        day,
        phase_started_on=phase_started_on,
        observed_file=observed_file,
        daily_file=daily_file,
    )
