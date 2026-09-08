#!/usr/bin/env python3
"""Fail-closed P1 contracts for C1 V2 candidates.

The upstream parser already filters unreliable station declarations. This module is a
second, independent publication boundary: even if a malformed fixture reaches promotion,
new public rows must remain plausible, contiguous, mutually aligned and internally
coherent. It also refreshes/validates publication metadata that must follow the actual
candidate cutoff.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math

import c1_last_date
import enrich_data_meta
import shield_phase_v2
import station_audit
import update_data_v2 as core

REQUIRED_FUELS = ("G", "S")
REQUIRED_BOUCLIER_FUELS = ("Gazole", "SP95")
VALUE_TOLERANCE = 0.0021  # published values are rounded to 0.001 €/L
AGGREGATE_TOLERANCE = 0.0021


def _fail(message: str) -> None:
    raise ValueError(message)


def _finite(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric value {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite value {value!r}")
    return number


def _last_offset(rows: list[list], label: str) -> int:
    if not isinstance(rows, list) or not rows:
        _fail(f"empty daily series: {label}")
    try:
        return int(rows[-1][0])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"invalid last daily row: {label}") from exc


def _target_offset(candidate: dict) -> int:
    raw = ((candidate.get("meta") or {}).get("last_date"))
    try:
        day = date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValueError(f"invalid meta.last_date: {raw!r}") from exc
    return (day - core.ORIGIN).days


def _row_map(rows: list[list]) -> dict[int, list]:
    out = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            _fail(f"invalid daily row shape: {row!r}")
        try:
            off = int(row[0])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid daily offset: {row!r}") from exc
        if off in out:
            _fail(f"duplicate daily offset: {off}")
        out[off] = row
    return out


def _validate_new_row(short: str, region: str, row: list) -> None:
    ttc = _finite(row[1])
    ht = _finite(row[2])
    if not core.PRICE_MIN <= ttc <= core.PRICE_MAX:
        _fail(f"{short}/{region}: TTC {ttc:.3f} outside {core.PRICE_MIN:.2f}-{core.PRICE_MAX:.2f} €/L")
    if ht < 0:
        _fail(f"{short}/{region}: negative HT {ht:.3f} €/L")
    vat = 1.13 if region == "corse" else 1.20
    expected_ht = ttc / vat
    if abs(ht - expected_ht) > VALUE_TOLERANCE:
        _fail(
            f"{short}/{region}: HT/TTC incoherent: TTC={ttc:.3f}, HT={ht:.3f}, "
            f"expected≈{expected_ht:.3f}"
        )


def validate_appended_daily_contract(baseline: dict, candidate: dict) -> None:
    """Validate only the newly appended daily tail, independently of the builder."""
    target_off = _target_offset(candidate)
    first_new_by_fuel: dict[str, int | None] = {}

    for short in REQUIRED_FUELS:
        old_regions = baseline.get(short) or {}
        new_regions = candidate.get(short) or {}
        if set(old_regions) != set(new_regions):
            _fail(f"{short}: region topology changed")

        fuel_first_new = None
        for region in old_regions:
            old_rows = old_regions[region].get("d") or []
            new_rows = new_regions[region].get("d") or []
            old_last = _last_offset(old_rows, f"{short}/{region}")
            new_last = _last_offset(new_rows, f"{short}/{region}")
            if new_last != target_off:
                _fail(
                    f"{short}/{region}: isolated daily endpoint {new_last}; "
                    f"publication cutoff is {target_off}"
                )
            if new_last < old_last:
                _fail(f"{short}/{region}: candidate daily series shrank")

            old_map = _row_map(old_rows)
            new_map = _row_map(new_rows)
            if new_last > old_last:
                expected = list(range(old_last + 1, new_last + 1))
                actual = sorted(off for off in new_map if off > old_last)
                if actual != expected:
                    _fail(f"{short}/{region}: non-contiguous appended daily tail: {actual[:3]}…")
                for off in expected:
                    _validate_new_row(short, region, new_map[off])
                first = old_last + 1
                fuel_first_new = first if fuel_first_new is None else min(fuel_first_new, first)
            elif target_off > old_last:
                _fail(f"{short}/{region}: series did not advance to publication cutoff")

            if any(off <= old_last and off not in old_map for off in new_map):
                _fail(f"{short}/{region}: inserted historical daily key")

        first_new_by_fuel[short] = fuel_first_new

    starts = {v for v in first_new_by_fuel.values() if v is not None}
    if len(starts) > 1:
        _fail(f"Gazole/SP95 appended windows diverge: {first_new_by_fuel}")

    for short in REQUIRED_FUELS:
        first_new = first_new_by_fuel[short]
        if first_new is None:
            continue
        maps = {
            region: _row_map(candidate[short][region]["d"])
            for region in ["moy_regions"] + core.REGIONS
        }
        for off in range(first_new, target_off + 1):
            region_rows = []
            for region in core.REGIONS:
                r = maps[region].get(off)
                if r is None:
                    _fail(f"{short}/{region}: missing regional row at offset {off}")
                region_rows.append(r)
            aggregate = maps["moy_regions"].get(off)
            if aggregate is None:
                _fail(f"{short}/moy_regions: missing aggregate row at offset {off}")
            expected_ttc = sum(float(r[1]) for r in region_rows) / len(region_rows)
            expected_ht = expected_ttc / 1.20
            if abs(float(aggregate[1]) - expected_ttc) > AGGREGATE_TOLERANCE:
                _fail(
                    f"{short}/moy_regions: TTC aggregate incoherent at offset {off}: "
                    f"{aggregate[1]} vs {expected_ttc:.3f}"
                )
            if abs(float(aggregate[2]) - expected_ht) > AGGREGATE_TOLERANCE:
                _fail(
                    f"{short}/moy_regions: HT aggregate incoherent at offset {off}: "
                    f"{aggregate[2]} vs {expected_ht:.3f}"
                )


def validate_publication_metadata(candidate: dict) -> None:
    meta = candidate.get("meta") or {}
    last_date = meta.get("last_date")
    if not last_date:
        _fail("missing meta.last_date")
    editorial = meta.get("editorial") or {}
    for fuel in REQUIRED_BOUCLIER_FUELS:
        node = editorial.get(fuel) or {}
        if node.get("through") != last_date:
            _fail(f"editorial.{fuel}.through={node.get('through')!r} != {last_date}")
    audit = meta.get("station_audit") or {}
    if audit.get("as_of") != last_date:
        _fail(f"station_audit.as_of={audit.get('as_of')!r} != {last_date}")


def _expected_phase_json(bmeta: dict, fuel: str) -> list[dict]:
    try:
        phases = shield_phase_v2.phases_from_bouclier_metadata(bmeta).get(fuel, [])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"bouclier.{fuel}: cannot derive cap phases") from exc
    return [
        {
            "d1": p.started_on.isoformat(),
            "d2": p.ended_on.isoformat(),
            "cap": p.cap,
            "phase_id": f"{fuel}:{p.started_on.isoformat()}:{p.cap:.3f}",
        }
        for p in phases
    ]


def validate_bouclier_contract(meta: dict) -> None:
    last_date = meta.get("last_date")
    bmeta = meta.get("bouclier")
    if not isinstance(bmeta, dict):
        _fail("missing bouclier metadata")
    required = (
        "ranges",
        "phases",
        "current_active",
        "current_active_since",
        "current_cap",
        "evaluated_through",
        "latest_total_stations",
        "latest_non_total_stations",
        "latest_at_cap_count",
        "latest_non_total_p75",
        "rule",
    )
    for fuel in REQUIRED_BOUCLIER_FUELS:
        node = bmeta.get(fuel)
        if not isinstance(node, dict):
            _fail(f"missing bouclier metadata for {fuel}")
        for field in required:
            if field not in node:
                _fail(f"bouclier.{fuel}.{field} missing")
        if node["evaluated_through"] != last_date:
            _fail(
                f"bouclier.{fuel}.evaluated_through={node['evaluated_through']!r} != {last_date}"
            )
        if not isinstance(node["ranges"], list):
            _fail(f"bouclier.{fuel}.ranges is not a list")
        if not isinstance(node["current_active"], bool):
            _fail(f"bouclier.{fuel}.current_active is not boolean")

        try:
            evaluated_day = date.fromisoformat(str(node["evaluated_through"]))
        except ValueError as exc:
            raise ValueError(
                f"bouclier.{fuel}.evaluated_through invalid: {node['evaluated_through']!r}"
            ) from exc

        parsed_ranges: list[tuple[date, date]] = []
        previous_end = None
        for item in node["ranges"]:
            try:
                start = date.fromisoformat(item["d1"])
                end = date.fromisoformat(item["d2"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"bouclier.{fuel}: invalid range {item!r}") from exc
            if start > end:
                _fail(f"bouclier.{fuel}: inverted range {item!r}")
            if previous_end is not None and start <= previous_end:
                _fail(f"bouclier.{fuel}: overlapping/unordered ranges")
            parsed_ranges.append((start, end))
            previous_end = end

        expected_phases = _expected_phase_json(bmeta, fuel)
        if node["phases"] != expected_phases:
            _fail(
                f"bouclier.{fuel}.phases inconsistent with ranges/cap schedule: "
                f"expected={expected_phases!r} actual={node['phases']!r}"
            )
        if not isinstance(node["rule"], dict) or not node["rule"]:
            _fail(f"bouclier.{fuel}.rule missing")
        for field in ("latest_total_stations", "latest_non_total_stations", "latest_at_cap_count"):
            value = node[field]
            if not isinstance(value, int) or value < 0:
                _fail(f"bouclier.{fuel}.{field} invalid: {value!r}")
        if node["latest_non_total_p75"] is None:
            _fail(f"bouclier.{fuel}.latest_non_total_p75 missing")

        covering_range = next(
            ((start, end) for start, end in parsed_ranges if start <= evaluated_day <= end),
            None,
        )
        if node["current_active"]:
            if covering_range is None:
                _fail(
                    f"bouclier.{fuel}: active but no effective range covers {evaluated_day}"
                )
            if not node["current_active_since"]:
                _fail(f"bouclier.{fuel}: active without current_active_since")
            try:
                active_since = date.fromisoformat(str(node["current_active_since"]))
            except ValueError as exc:
                raise ValueError(
                    f"bouclier.{fuel}.current_active_since invalid: {node['current_active_since']!r}"
                ) from exc
            if active_since != covering_range[0]:
                _fail(
                    f"bouclier.{fuel}: current_active_since={active_since} does not match "
                    f"covering range start {covering_range[0]}"
                )
            if node["current_cap"] is None:
                _fail(f"bouclier.{fuel}: active without current_cap")
            phase = shield_phase_v2.phase_for_day(bmeta, fuel, evaluated_day)
            if phase is None:
                _fail(f"bouclier.{fuel}: active without a cap phase on {evaluated_day}")
            current_cap = _finite(node["current_cap"])
            if abs(current_cap - float(phase.cap)) > 1e-9:
                _fail(
                    f"bouclier.{fuel}: current_cap={current_cap:.3f} does not match "
                    f"effective phase cap {phase.cap:.3f} on {evaluated_day}"
                )
            if node["latest_at_cap_count"] < 1:
                _fail(f"bouclier.{fuel}: active without a Total station at cap")
        elif covering_range is not None:
            _fail(
                f"bouclier.{fuel}: inactive but effective range covers {evaluated_day}"
            )


def refresh_publication_metadata(candidate: dict, baseline: dict, summary: dict) -> tuple[dict, dict]:
    """Refresh metadata derived from the actual candidate, without touching fuel history."""
    out = deepcopy(candidate)
    summary_out = deepcopy(summary)
    meta = out.setdefault("meta", {})
    last_date = c1_last_date.latest_daily_date(out)
    meta["last_date"] = last_date
    year = date.fromisoformat(last_date).year

    bmeta = meta.get("bouclier") or {}
    summary_bmeta = ((summary_out.get("engine") or {}).get("bouclier") or {})
    for fuel in REQUIRED_BOUCLIER_FUELS:
        if not isinstance(bmeta.get(fuel), dict):
            _fail(f"cannot refresh absent bouclier metadata for {fuel}")
        bmeta[fuel]["evaluated_through"] = last_date
        if isinstance(summary_bmeta.get(fuel), dict):
            summary_bmeta[fuel]["evaluated_through"] = last_date
    meta["bouclier"] = bmeta

    action_ranges = enrich_data_meta.total_action_ranges(bmeta, year)
    meta["editorial_action_rule"] = "union-of-gazole-and-sp95-total-intervention-periods"
    meta["editorial"] = {
        "Gazole": enrich_data_meta.editorial_for(
            out, "G", "Gazole", bmeta["Gazole"], year, action_ranges
        ),
        "SP95": enrich_data_meta.editorial_for(
            out, "S", "SP95", bmeta["SP95"], year, action_ranges
        ),
    }

    audit = station_audit.build_audit(out, year)
    previous = ((baseline.get("meta") or {}).get("station_audit"))
    station_audit.validate_audit(audit, previous)
    meta["station_audit"] = audit
    return out, summary_out


def validate_all(baseline: dict, candidate: dict) -> None:
    validate_appended_daily_contract(baseline, candidate)
    validate_publication_metadata(candidate)
    validate_bouclier_contract(candidate.get("meta") or {})
