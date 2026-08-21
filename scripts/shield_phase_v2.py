#!/usr/bin/env python3
"""Prepared helper to split effective-shield ranges into cap phases.

A cap phase is a contiguous period during which:
- the independently detected shield remains effective; and
- the applicable TotalEnergies cap for the fuel does not change.

R2 is deliberately absent from phase construction. Rotterdam never starts or
ends an effective-shield phase. For R2, the relevant anchor is the start of the
current *double-cap effective period*, i.e. when Gazole and SP95 phases overlap.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

import bouclier_detector


@dataclass(frozen=True)
class ShieldPhase:
    fuel: str
    started_on: date
    ended_on: date
    cap: float


@dataclass(frozen=True)
class DoubleCapPeriod:
    started_on: date
    ended_on: date
    gazole_cap: float
    sp95_cap: float


def _as_date(raw: str | date) -> date:
    return raw if isinstance(raw, date) else date.fromisoformat(str(raw))


def split_range(fuel: str, start: date, end: date) -> list[ShieldPhase]:
    if end < start:
        raise ValueError("shield range end before start")
    phases: list[ShieldPhase] = []
    phase_start = start
    phase_cap = bouclier_detector.cap_for(fuel, start)
    if phase_cap is None:
        raise ValueError(f"No cap for {fuel} on effective-shield start {start}")

    d = start + timedelta(days=1)
    while d <= end:
        cap = bouclier_detector.cap_for(fuel, d)
        if cap is None:
            raise ValueError(f"No cap for {fuel} during effective-shield range on {d}")
        if float(cap) != float(phase_cap):
            phases.append(ShieldPhase(fuel, phase_start, d - timedelta(days=1), float(phase_cap)))
            phase_start = d
            phase_cap = cap
        d += timedelta(days=1)
    phases.append(ShieldPhase(fuel, phase_start, end, float(phase_cap)))
    return phases


def phases_from_bouclier_metadata(metadata: Mapping) -> dict[str, list[ShieldPhase]]:
    result: dict[str, list[ShieldPhase]] = {}
    for fuel in ("Gazole", "SP95"):
        fuel_meta = metadata.get(fuel, {}) if isinstance(metadata, Mapping) else {}
        ranges = fuel_meta.get("ranges", []) if isinstance(fuel_meta, Mapping) else []
        phases: list[ShieldPhase] = []
        for item in ranges:
            if not isinstance(item, Mapping):
                continue
            start = _as_date(item["d1"])
            end = _as_date(item["d2"])
            phases.extend(split_range(fuel, start, end))
        result[fuel] = phases
    return result


def with_cap_phases(metadata: Mapping) -> dict:
    """Return a JSON-ready copy of shield metadata with explicit cap phases."""
    out = deepcopy(dict(metadata))
    all_phases = phases_from_bouclier_metadata(metadata)
    for fuel, phases in all_phases.items():
        out.setdefault(fuel, {})["phases"] = [
            {
                "d1": p.started_on.isoformat(),
                "d2": p.ended_on.isoformat(),
                "cap": p.cap,
                "phase_id": f"{fuel}:{p.started_on.isoformat()}:{p.cap:.3f}",
            }
            for p in phases
        ]
    return out


def phase_for_day(metadata: Mapping, fuel: str, day: date) -> ShieldPhase | None:
    """Locate the effective cap phase for one day; None means shield not effective."""
    for phase in phases_from_bouclier_metadata(metadata).get(fuel, []):
        if phase.started_on <= day <= phase.ended_on:
            return phase
    return None


def double_cap_period_for_day(metadata: Mapping, day: date) -> DoubleCapPeriod | None:
    """Return the overlapping Gazole+SP95 effective period containing ``day``.

    Its start is the later of the two fuel-phase starts. This is the date used
    to choose the three observed Rotterdam quotations for the phase-specific R1.
    """
    gazole = phase_for_day(metadata, "Gazole", day)
    sp95 = phase_for_day(metadata, "SP95", day)
    if gazole is None or sp95 is None:
        return None
    start = max(gazole.started_on, sp95.started_on)
    end = min(gazole.ended_on, sp95.ended_on)
    if not (start <= day <= end):
        return None
    return DoubleCapPeriod(start, end, gazole.cap, sp95.cap)
