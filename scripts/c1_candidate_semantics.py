#!/usr/bin/env python3
"""Independent semantic checks for the mutable C1 V2 publication tail."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math

import update_data_v2 as core

TOLERANCE = 0.0021


def _fail(message: str) -> None:
    raise ValueError(message)


def _finite(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: non-numeric value {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}: non-finite value {value!r}")
    return number


def _bucket(day: date, granularity: str):
    if granularity == "w":
        monday = day - timedelta(days=day.weekday())
        return (monday - core.ORIGIN).days
    if granularity == "m":
        return f"{day.year:04d}-{day.month:02d}"
    raise ValueError(granularity)


def _aggregate_from_daily(rows: list[list], granularity: str) -> dict[object, tuple[float, float]]:
    groups: dict[object, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            _fail(f"invalid daily row for {granularity}: {row!r}")
        try:
            off = int(row[0])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid daily offset for {granularity}: {row!r}") from exc
        day = core.ORIGIN + timedelta(days=off)
        groups[_bucket(day, granularity)].append(
            (_finite(row[1], "daily TTC"), _finite(row[2], "daily HT"))
        )
    return {
        key: (
            sum(ttc for ttc, _ in values) / len(values),
            sum(ht for _, ht in values) / len(values),
        )
        for key, values in groups.items()
    }


def _actual_aggregate(rows: list[list], label: str) -> dict[object, tuple[float, float]]:
    out = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            _fail(f"{label}: invalid aggregate row {row!r}")
        key = row[0]
        if key in out:
            _fail(f"{label}: duplicate aggregate key {key!r}")
        out[key] = (_finite(row[1], f"{label} TTC"), _finite(row[2], f"{label} HT"))
    return out


def validate_mutable_aggregates(
    baseline: dict,
    candidate: dict,
    first_new_day: date | None,
) -> None:
    """Rebuild every mutable weekly/monthly bucket from candidate daily rows.

    Historical buckets before the first appended day remain governed by the promoter's
    append-only prefix check. Buckets that are allowed to change must be numerically
    consistent with the daily series that will actually be published.
    """
    if first_new_day is None:
        return

    for short in ("G", "S"):
        old_regions = baseline.get(short) or {}
        new_regions = candidate.get(short) or {}
        if set(old_regions) != set(new_regions):
            _fail(f"{short}: region topology changed before aggregate validation")
        for region in old_regions:
            daily = (new_regions.get(region) or {}).get("d") or []
            for granularity in ("w", "m"):
                boundary = _bucket(first_new_day, granularity)
                expected = _aggregate_from_daily(daily, granularity)
                actual = _actual_aggregate(
                    (new_regions.get(region) or {}).get(granularity) or [],
                    f"{short}/{region}/{granularity}",
                )
                expected_tail = {k: v for k, v in expected.items() if k >= boundary}
                actual_tail = {k: v for k, v in actual.items() if k >= boundary}
                if set(expected_tail) != set(actual_tail):
                    _fail(
                        f"{short}/{region}/{granularity}: mutable aggregate keys differ: "
                        f"expected={sorted(expected_tail)} actual={sorted(actual_tail)}"
                    )
                for key, (expected_ttc, expected_ht) in expected_tail.items():
                    actual_ttc, actual_ht = actual_tail[key]
                    if abs(actual_ttc - expected_ttc) > TOLERANCE:
                        _fail(
                            f"{short}/{region}/{granularity}: TTC aggregate incoherent at {key}: "
                            f"{actual_ttc:.3f} vs daily mean {expected_ttc:.3f}"
                        )
                    if abs(actual_ht - expected_ht) > TOLERANCE:
                        _fail(
                            f"{short}/{region}/{granularity}: HT aggregate incoherent at {key}: "
                            f"{actual_ht:.3f} vs daily mean {expected_ht:.3f}"
                        )


def validate_summary_cutoff(candidate: dict, summary: dict) -> None:
    """Bind the production summary/source cutoff to the actual candidate endpoint."""
    last_date = str(((candidate.get("meta") or {}).get("last_date")) or "")
    target_end = str(summary.get("target_end") or "")
    source_max = str(((summary.get("engine") or {}).get("source_max_date")) or "")
    if not last_date:
        _fail("candidate has no meta.last_date")
    if target_end != last_date:
        _fail(f"summary target_end={target_end!r} != candidate last_date={last_date!r}")
    try:
        target_day = date.fromisoformat(target_end)
        source_day = date.fromisoformat(source_max)
    except ValueError as exc:
        raise ValueError(
            f"invalid summary cutoff dates: target_end={target_end!r} source_max={source_max!r}"
        ) from exc
    if source_day < target_day:
        _fail(f"source_max_date={source_max} is older than published target_end={target_end}")
