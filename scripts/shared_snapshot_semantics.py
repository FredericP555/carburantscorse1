#!/usr/bin/env python3
"""Semantic validation for the C1 -> C2 shared official snapshot and shield metadata."""
from __future__ import annotations

from collections import Counter
from datetime import date
import csv
import gzip
import math
from pathlib import Path

REQUIRED_COLUMNS = {"source_year", "station_id", "department", "fuel", "date"}
REQUIRED_DEPARTMENTS = {"13", "20"}
REQUIRED_FUELS = {"Gazole", "SP95", "E10"}


def _fail(message: str) -> None:
    raise RuntimeError(message)


def _finite_positive(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise RuntimeError(f"Invalid {label}: {value!r}")
    return number


def _normalized_counter(value) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): int(v) for k, v in value.items()}


def validate_snapshot_semantics(meta: dict, snapshot: Path) -> None:
    rows = 0
    min_date = None
    max_date = None
    by_year = Counter()
    by_department = Counter()
    by_fuel = Counter()

    with gzip.open(snapshot, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            _fail("Shared snapshot CSV schema is incomplete")
        for row in reader:
            rows += 1
            raw_date = str(row.get("date") or "")
            try:
                day = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise RuntimeError(f"Invalid shared snapshot date: {raw_date!r}") from exc
            source_year = str(row.get("source_year") or "")
            department = str(row.get("department") or "")
            fuel = str(row.get("fuel") or "")
            if department not in REQUIRED_DEPARTMENTS:
                _fail(f"Unexpected department in shared snapshot: {department!r}")
            if fuel not in REQUIRED_FUELS:
                _fail(f"Unexpected fuel in shared snapshot: {fuel!r}")
            if source_year != str(day.year):
                _fail(
                    f"Shared snapshot source_year/date mismatch: year={source_year!r} date={raw_date!r}"
                )
            min_date = raw_date if min_date is None or raw_date < min_date else min_date
            max_date = raw_date if max_date is None or raw_date > max_date else max_date
            by_year[source_year] += 1
            by_department[department] += 1
            by_fuel[fuel] += 1

    if rows <= 0:
        _fail("Shared snapshot contains no price rows")
    if rows != int(meta.get("rows", -1)):
        _fail(f"Shared snapshot row count mismatch: actual={rows} manifest={meta.get('rows')!r}")
    if min_date != meta.get("min_date") or max_date != meta.get("max_date"):
        _fail(
            f"Shared snapshot date bounds mismatch: actual={min_date}..{max_date} "
            f"manifest={meta.get('min_date')!r}..{meta.get('max_date')!r}"
        )
    if _normalized_counter(meta.get("rows_by_year")) != dict(by_year):
        _fail("Shared snapshot rows_by_year mismatch")
    if _normalized_counter(meta.get("rows_by_department")) != dict(by_department):
        _fail("Shared snapshot rows_by_department mismatch")
    if _normalized_counter(meta.get("rows_by_fuel")) != dict(by_fuel):
        _fail("Shared snapshot rows_by_fuel mismatch")

    actual_years = sorted(int(x) for x in by_year)
    declared_years = sorted(int(x) for x in (meta.get("years") or []))
    if actual_years != declared_years:
        _fail(f"Shared snapshot years mismatch: actual={actual_years} manifest={declared_years}")
    if set(by_department) != set(str(x) for x in (meta.get("departments") or [])):
        _fail("Shared snapshot department population mismatch")
    if set(by_fuel) != set(str(x) for x in (meta.get("fuels") or [])):
        _fail("Shared snapshot fuel population mismatch")


def validate_bouclier_semantics(bouclier: dict, max_date: str) -> None:
    if not isinstance(bouclier, dict):
        _fail("Missing effective-shield metadata")
    try:
        evaluated_day = date.fromisoformat(str(max_date))
    except ValueError as exc:
        raise RuntimeError(f"Invalid shared snapshot max_date: {max_date!r}") from exc

    for fuel in ("Gazole", "SP95"):
        node = bouclier.get(fuel)
        if not isinstance(node, dict):
            _fail(f"Missing shield metadata for {fuel}")
        if "ranges" not in node or not isinstance(node.get("ranges"), list):
            _fail(f"Missing/invalid shield ranges for {fuel}")
        if "phases" not in node or not isinstance(node.get("phases"), list):
            _fail(f"Missing/invalid shield phases for {fuel}")
        if not isinstance(node.get("current_active"), bool):
            _fail(f"Invalid current_active for {fuel}")

        ranges: list[tuple[date, date]] = []
        previous_end = None
        for item in node["ranges"]:
            try:
                start = date.fromisoformat(str(item["d1"]))
                end = date.fromisoformat(str(item["d2"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid shield range for {fuel}: {item!r}") from exc
            if end < start:
                _fail(f"Inverted shield range for {fuel}: {item!r}")
            if previous_end is not None and start <= previous_end:
                _fail(f"Overlapping shield ranges for {fuel}")
            ranges.append((start, end))
            previous_end = end

        phases: list[tuple[date, date, float]] = []
        for item in node["phases"]:
            try:
                start = date.fromisoformat(str(item["d1"]))
                end = date.fromisoformat(str(item["d2"]))
                cap = _finite_positive(item["cap"], f"{fuel} cap")
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid shield phase for {fuel}: {item!r}") from exc
            if end < start:
                _fail(f"Inverted shield phase for {fuel}: {item!r}")
            if not any(r1 <= start and end <= r2 for r1, r2 in ranges):
                _fail(f"Shield phase for {fuel} is not contained in an effective range: {item!r}")
            phases.append((start, end, cap))

        covering_range = next(
            ((start, end) for start, end in ranges if start <= evaluated_day <= end),
            None,
        )
        if node["current_active"]:
            if covering_range is None:
                _fail(f"{fuel} shield is active but max_date is outside all ranges")
            try:
                active_since = date.fromisoformat(str(node.get("current_active_since")))
            except ValueError as exc:
                raise RuntimeError(f"Invalid current_active_since for {fuel}") from exc
            if active_since != covering_range[0]:
                _fail(f"{fuel} current_active_since does not match covering range")
            current_cap = _finite_positive(node.get("current_cap"), f"{fuel} current cap")
            covering_phase = next(
                ((start, end, cap) for start, end, cap in phases if start <= evaluated_day <= end),
                None,
            )
            if covering_phase is None:
                _fail(f"{fuel} shield is active but max_date has no cap phase")
            if abs(current_cap - covering_phase[2]) > 1e-9:
                _fail(f"{fuel} current cap does not match covering phase")
        elif covering_range is not None:
            _fail(f"{fuel} shield is inactive but max_date lies inside an effective range")
