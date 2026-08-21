#!/usr/bin/env python3
"""Prepared Corsica R2 guard derived directly from the target declaration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import rotterdam_corse_shared_v2 as rotterdam

NORMAL_MAX_AGE_DAYS = 45


def stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    *,
    observed_file: str | Path = rotterdam.OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DAILY_FILE,
) -> bool:
    """Return the R2 verdict without accepting a caller-computed start day.

    J0..J+44 do not need the R2 exception and return True here.  From J+45,
    the complete Rotterdam window is checked.  A new target declaration changes
    ``last_declared_at`` and therefore resets the window automatically.
    """
    if last_declared_at is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day:
        return False
    stale_start = declared_on + timedelta(days=NORMAL_MAX_AGE_DAYS)
    if day < stale_start:
        return True
    return rotterdam.admissible_since(
        stale_start,
        day,
        observed_file=observed_file,
        daily_file=daily_file,
    )
