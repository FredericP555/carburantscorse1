#!/usr/bin/env python3
"""Prepared helper to split effective-shield ranges into cap phases.

A cap phase is a contiguous period during which:
- the independently detected shield remains effective; and
- the applicable TotalEnergies cap for the fuel does not change.

R2 is deliberately absent from phase construction. Rotterdam never starts or
ends an effective-shield phase.
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
