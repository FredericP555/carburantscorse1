#!/usr/bin/env python3
"""Audit Corsica station eligibility before publishing a weekly update.

The dashboard average is built from station-fuel series after three filters:
- motorway stations (pop=A) are already discarded by update_data_v2.parse_year();
- a station whose last declaration is older than MAX_FFILL_DAYS is stale and excluded;
- a station whose latest declaration is numerically suspect is excluded until a later valid declaration.

This script reconstructs the exact latest-day eligibility state for Corsica, stores the audit in
``data-candidate.json`` and applies guardrails before publication.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

ORIGIN = core.ORIGIN
MIN_RETAINED = {"Gazole": 80, "SP95": 60}
MAX_RETAINED_DROP = 0.20
MAX_INVALID_SHARE = 0.05
# First verified audit, used only until data.json contains its own previous audit baseline.
BOOTSTRAP_AS_OF = date(2026, 8, 17)
BOOTSTRAP_RETAINED = {"Gazole": 121, "SP95": 106}


def candidate_last_date(data: dict) -> date:
    offs = []
    for short in ("G", "S"):
        pts = data[short]["corse"]["d"]
        if not pts:
            raise RuntimeError(f"Empty Corse daily series: {short}")
        offs.append(pts[-1][0])
    if len(set(offs)) != 1:
        raise RuntimeError(f"Gazole/SP95 candidate cutoffs diverge: {offs}")
    return ORIGIN + timedelta(days=offs[0])


def load_changes(year: int):
    changes = defaultdict(list)
    for y in (year - 1, year):
        for key, vals in core.parse_year(y).items():
            changes[key].extend(vals)
    return changes


def latest_daily_update(vals, as_of: date):
    """Return the last declaration on/before as_of, with last declaration of a day winning."""
    per_day = {}
    for ts, value in vals:
        if ts.date() <= as_of:
            per_day[ts.date()] = (ts, value)
    if not per_day:
        return None
    return max(per_day.values(), key=lambda x: x[0])


def audit_fuel(changes, fuel: str, year: int, as_of: date):
    station_vals = {
        sid: vals
        for (sid, region, f), vals in changes.items()
        if region == "corse" and f == fuel
    }

    retained = []
    stale = []
    invalid = []
    no_prior = []
    declared_current_year = 0

    for sid, vals in sorted(station_vals.items()):
        if any(ts.year == year and ts.date() <= as_of for ts, _ in vals):
            declared_current_year += 1

        latest = latest_daily_update(vals, as_of)
        if latest is None:
            no_prior.append({"station_id": sid})
            continue

        ts, value = latest
        age = (as_of - ts.date()).days
        detail = {
            "station_id": sid,
            "last_date": str(ts.date()),
            "age_days": age,
        }

        # Match build_daily(): age is checked before the invalid-state test.
        if age > core.MAX_FFILL_DAYS:
            stale.append(detail)
        elif value is None:
            invalid.append(detail)
        else:
            retained.append(detail)

    known = len(station_vals)
    reconciled = len(retained) + len(stale) + len(invalid) + len(no_prior)
    if reconciled != known:
        raise RuntimeError(f"Audit reconciliation failed for {fuel}: {reconciled} != {known}")

    previous_year_only = known - declared_current_year
    return {
        "known_station_fuel_series": known,
        "declared_current_year": declared_current_year,
        "previous_year_only": previous_year_only,
        "retained": len(retained),
        "excluded_stale": len(stale),
        "excluded_invalid_latest": len(invalid),
        "excluded_no_prior": len(no_prior),
        "retained_share": round(len(retained) / known, 4) if known else None,
        "excluded_stale_ids": stale,
        "excluded_invalid_ids": invalid,
        "excluded_no_prior_ids": no_prior,
    }


def build_audit(candidate: dict, year: int):
    as_of = candidate_last_date(candidate)
    if as_of.year != year:
        raise RuntimeError(f"Candidate year {as_of.year} differs from requested audit year {year}")
    changes = load_changes(year)
    fuels = {fuel: audit_fuel(changes, fuel, year, as_of) for fuel in ("Gazole", "SP95")}
    return {
        "as_of": str(as_of),
        "scope": "Corse, hors stations pop=A, Gazole/SP95, stocks annuels N-1 et N",
        "max_ffill_days": core.MAX_FFILL_DAYS,
        "guardrails": {
            "minimum_retained": MIN_RETAINED,
            "maximum_retained_drop_vs_previous_audit": MAX_RETAINED_DROP,
            "maximum_invalid_latest_share": MAX_INVALID_SHARE,
            "bootstrap_reference": {
                "as_of": str(BOOTSTRAP_AS_OF),
                "retained": BOOTSTRAP_RETAINED,
            },
        },
        "fuels": fuels,
    }


def validate_audit(audit: dict, previous: dict | None):
    as_of = date.fromisoformat(audit["as_of"])
    for fuel in ("Gazole", "SP95"):
        a = audit["fuels"][fuel]
        known = a["known_station_fuel_series"]
        retained = a["retained"]
        invalid = a["excluded_invalid_latest"]

        if known <= 0:
            raise RuntimeError(f"No Corsica station-fuel series found for {fuel}")
        if retained < MIN_RETAINED[fuel]:
            raise RuntimeError(
                f"Coverage guardrail failed for {fuel}: retained={retained} < {MIN_RETAINED[fuel]}"
            )
        if invalid / known > MAX_INVALID_SHARE:
            raise RuntimeError(
                f"Too many latest invalid prices for {fuel}: {invalid}/{known} > {MAX_INVALID_SHARE:.0%}"
            )

        # Prefer the last published audit. Before the first audited publication, use the
        # verified 17 Aug 2026 population so the very first production run is also protected.
        reference = None
        label = None
        if previous:
            prev = previous.get("fuels", {}).get(fuel)
            if prev and prev.get("retained"):
                reference = int(prev["retained"])
                label = f"previous audit {previous.get('as_of', '?')}"
        if reference is None and as_of >= BOOTSTRAP_AS_OF:
            reference = BOOTSTRAP_RETAINED[fuel]
            label = f"bootstrap audit {BOOTSTRAP_AS_OF}"

        if reference:
            drop = (reference - retained) / reference
            if drop > MAX_RETAINED_DROP:
                raise RuntimeError(
                    f"Sudden retained-station drop for {fuel}: {reference} -> {retained} "
                    f"({drop:.1%}) vs {label}"
                )


def print_report(audit: dict):
    print(f"STATION AUDIT — Corse — {audit['as_of']}")
    for fuel in ("Gazole", "SP95"):
        a = audit["fuels"][fuel]
        print(
            f"{fuel}: known={a['known_station_fuel_series']}, "
            f"declared_current_year={a['declared_current_year']}, retained={a['retained']}, "
            f"stale={a['excluded_stale']}, invalid_latest={a['excluded_invalid_latest']}, "
            f"no_prior={a['excluded_no_prior']}"
        )
        if a["excluded_invalid_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_invalid_ids"])
            print(f"  invalid latest IDs: {ids}")
        if a["excluded_stale_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_stale_ids"][:20])
            suffix = " ..." if len(a["excluded_stale_ids"]) > 20 else ""
            print(f"  stale IDs: {ids}{suffix}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="data-candidate.json")
    ap.add_argument("--previous", default="data.json")
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--write-meta", action="store_true")
    args = ap.parse_args()

    candidate_path = Path(args.candidate)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    audit = build_audit(candidate, args.year)

    previous_audit = None
    previous_path = Path(args.previous)
    if previous_path.exists():
        previous_data = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_audit = (previous_data.get("meta") or {}).get("station_audit")

    validate_audit(audit, previous_audit)
    print_report(audit)

    if args.write_meta:
        candidate.setdefault("meta", {})["station_audit"] = audit
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"Stored station_audit in {candidate_path}")

    print("STATION AUDIT: OK")


if __name__ == "__main__":
    main()
