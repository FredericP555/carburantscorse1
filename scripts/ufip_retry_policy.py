#!/usr/bin/env python3
"""Deterministic policy for the conditional UFIP retry.

A retry is required when the previous week becomes complete, when a week that was already
complete changes semantically (date/value rows added, removed or corrected), or when the latest
C1 shared release predates the current explicit UFIP source contract. This catches both data
revisions and manifest migrations without treating formatting-only CSV differences as changes.
"""
from __future__ import annotations

from datetime import date, timedelta
import math

import pandas as pd

from a4c_common.ufip import (
    ROTTERDAM_REFERENCE_SOURCE,
    ROTTERDAM_SMOOTHING,
    ROTTERDAM_UNIT,
)


def release_contract_current(metadata: dict | None) -> bool:
    """Return whether a shared C1 manifest declares the exact UFIP contract C2 expects."""
    if not isinstance(metadata, dict):
        return False
    rotterdam = metadata.get("rotterdam")
    if not isinstance(rotterdam, dict):
        return False
    return (
        str(rotterdam.get("unit") or "") == ROTTERDAM_UNIT
        and str(rotterdam.get("reference_source") or "") == ROTTERDAM_REFERENCE_SOURCE
        and str(rotterdam.get("smoothing") or "") == ROTTERDAM_SMOOTHING
    )


def _week_rows(frame: pd.DataFrame, week_start: date) -> tuple[tuple[str, float], ...]:
    week_end = week_start + timedelta(days=6)
    if frame.empty or "date" not in frame.columns or "rotterdam_eur_l" not in frame.columns:
        return ()
    work = frame[["date", "rotterdam_eur_l"]].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.date
    work["rotterdam_eur_l"] = pd.to_numeric(work["rotterdam_eur_l"], errors="coerce")
    work = work[
        work["date"].notna()
        & work["rotterdam_eur_l"].notna()
        & work["date"].between(week_start, week_end)
    ].copy()
    if work.empty:
        return ()
    work = work.sort_values("date").drop_duplicates("date", keep="last")
    rows: list[tuple[str, float]] = []
    for row in work.itertuples(index=False):
        value = float(row.rotterdam_eur_l)
        if not math.isfinite(value) or value <= 0:
            continue
        rows.append((row.date.isoformat(), round(value, 8)))
    return tuple(rows)


def _complete(rows: tuple[tuple[str, float], ...], week_start: date) -> bool:
    if len(rows) < 3:
        return False
    dates = [date.fromisoformat(day) for day, _value in rows]
    return dates[0] <= week_start + timedelta(days=1) and dates[-1] >= week_start + timedelta(days=3)


def should_retry_week(
    baseline: pd.DataFrame,
    live: pd.DataFrame,
    week_start: date,
    *,
    release_meta: dict | None = None,
) -> dict:
    baseline_rows = _week_rows(baseline, week_start)
    live_rows = _week_rows(live, week_start)
    baseline_complete = _complete(baseline_rows, week_start)
    live_complete = _complete(live_rows, week_start)
    contract_current = None if release_meta is None else release_contract_current(release_meta)

    # Contract migration has priority once the live UFIP fetch itself succeeded. The weekly
    # production workflow will rebuild and validate the complete immutable C1 -> C2 bundle.
    if contract_current is False:
        ready = True
        reason = "release_contract_outdated"
    elif not live_complete:
        ready = False
        reason = "live_week_incomplete"
    elif not baseline_complete:
        ready = True
        reason = "week_became_complete"
    elif baseline_rows != live_rows:
        ready = True
        reason = "complete_week_values_changed"
    else:
        ready = False
        reason = "already_current"

    return {
        "ready": ready,
        "reason": reason,
        "baseline_complete": baseline_complete,
        "live_complete": live_complete,
        "baseline_rows": baseline_rows,
        "live_rows": live_rows,
        "release_contract_current": contract_current,
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
    }
