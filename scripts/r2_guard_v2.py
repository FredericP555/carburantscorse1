#!/usr/bin/env python3
"""Prepared Corsica R2 guard derived from declaration + double-cap period."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

import rotterdam_corse_shared_v2 as rotterdam
import shield_phase_v2 as shield_phase

NORMAL_MAX_AGE_DAYS = 45


def stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    *,
    bouclier_metadata: Mapping,
    observed_file: str | Path = rotterdam.OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DAILY_FILE,
) -> bool:
    """Return the persistent R2 verdict for the current double-cap period.

    The period anchor is derived internally from the overlapping Gazole and SP95
    effective phases. Its start is the later of their starts. This guarantees
    both old principal-fuel prices use the same phase-specific R2.
    """
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
    # Already stale when the double-cap period starts => no resurrection.
    if stale_start < period.started_on:
        return False
    return rotterdam.admissible_since(
        stale_start,
        day,
        phase_started_on=period.started_on,
        observed_file=observed_file,
        daily_file=daily_file,
    )
