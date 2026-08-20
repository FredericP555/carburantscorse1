#!/usr/bin/env python3
"""Audit Corsica station eligibility before publishing a weekly update.

Policy:
- motorway stations (pop=A) are already discarded by update_data_v2;
- the 45-day threshold applies to station activity, not to each fuel independently;
- while a station remains active, its last valid Gazole/SP95 price remains usable even when
  that fuel itself has not changed for more than 45 days;
- an active rupture suppresses the affected fuel;
- a suspicious latest price suppresses the affected fuel until a later valid declaration.

The audit deliberately records "old price / active station" cases instead of hiding them so
long-lived unchanged prices (notably capped SP95) remain visible to the weekly control.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

ORIGIN = core.ORIGIN
MIN_RETAINED = {"Gazole": 80, "SP95": 60}
MAX_RETAINED_DROP = 0.20
MAX_INVALID_SHARE = 0.05
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


def latest_daily_update(vals, as_of: date):
    """Return the last official declaration on/before as_of; last declaration of day wins."""
    per_day = {}
    for ts, value in vals:
        if ts.date() <= as_of:
            per_day[ts.date()] = (ts, value)
    if not per_day:
        return None
    return max(per_day.values(), key=lambda x: x[0])


def latest_activity(vals, as_of: date):
    eligible = [ts for ts in vals if ts.date() <= as_of]
    return max(eligible) if eligible else None


def audit_fuel(prices, activity, ruptures, fuel: str, year: int, as_of: date):
    station_vals = {
        sid: vals
        for (sid, region, f), vals in prices.items()
        if region == "corse" and f == fuel
    }

    retained = []
    retained_old_price = []
    inactive = []
    active_rupture = []
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
        price_age = (as_of - ts.date()).days
        station_ts = latest_activity(activity.get((sid, "corse"), []), as_of)
        station_age = (as_of - station_ts.date()).days if station_ts is not None else None
        detail = {
            "station_id": sid,
            "last_price_date": str(ts.date()),
            "price_age_days": price_age,
            "last_station_activity_date": str(station_ts.date()) if station_ts else None,
            "station_activity_age_days": station_age,
        }

        if not core.station_active(station_ts, as_of):
            inactive.append(detail)
        elif value is None:
            invalid.append(detail)
        elif core.rupture_active(ruptures.get((sid, "corse", fuel), []), as_of):
            active_rupture.append(detail)
        else:
            retained.append(detail)
            if price_age > core.MAX_STATION_INACTIVE_DAYS:
                retained_old_price.append(detail)

    known = len(station_vals)
    reconciled = (
        len(retained) + len(inactive) + len(active_rupture) + len(invalid) + len(no_prior)
    )
    if reconciled != known:
        raise RuntimeError(f"Audit reconciliation failed for {fuel}: {reconciled} != {known}")

    previous_year_only = known - declared_current_year
    return {
        "known_station_fuel_series": known,
        "declared_current_year": declared_current_year,
        "previous_year_only": previous_year_only,
        "retained": len(retained),
        "retained_old_price_active_station": len(retained_old_price),
        "excluded_inactive_station": len(inactive),
        "excluded_active_rupture": len(active_rupture),
        "excluded_invalid_latest": len(invalid),
        "excluded_no_prior": len(no_prior),
        "excluded_stale": len(inactive),
        "retained_share": round(len(retained) / known, 4) if known else None,
        "retained_old_price_active_station_ids": retained_old_price,
        "excluded_inactive_station_ids": inactive,
        "excluded_active_rupture_ids": active_rupture,
        "excluded_invalid_ids": invalid,
        "excluded_no_prior_ids": no_prior,
        "excluded_stale_ids": inactive,
    }


def build_audit(candidate: dict, year: int):
    as_of = candidate_last_date(candidate)
    if as_of.year != year:
        raise RuntimeError(f"Candidate year {as_of.year} differs from requested audit year {year}")
    prices, activity, ruptures = core.load_market_state(year)
    fuels = {
        fuel: audit_fuel(prices, activity, ruptures, fuel, year, as_of)
        for fuel in ("Gazole", "SP95")
    }
    return {
        "as_of": str(as_of),
        "scope": "Corse, hors stations pop=A, Gazole/SP95, stocks annuels N-1 et N",
        "station_activity_policy": True,
        "max_station_inactive_days": core.MAX_STATION_INACTIVE_DAYS,
        "max_ffill_days": core.MAX_STATION_INACTIVE_DAYS,
        "guardrails": {
            "minimum_retained": MIN_RETAINED,
            "maximum_retained_drop_vs_previous_audit": MAX_RETAINED_DROP,
            "maximum_invalid_latest_share": MAX_INVALID_SHARE,
            "bootstrap_reference": {
                "as_of": str(BOOTSTRAP_AS_OF),
                "retained": BOOTSTRAP_RETAINED,
                "note": "ancienne politique par anciennete du prix; conservee comme seuil bas historique",
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
    print(
        f"Policy: station activity <= {audit['max_station_inactive_days']} days; "
        "old unchanged fuel prices remain eligible while station stays active."
    )
    for fuel in ("Gazole", "SP95"):
        a = audit["fuels"][fuel]
        print(
            f"{fuel}: known={a['known_station_fuel_series']}, "
            f"declared_current_year={a['declared_current_year']}, retained={a['retained']}, "
            f"old_price_active_station={a['retained_old_price_active_station']}, "
            f"inactive_station={a['excluded_inactive_station']}, "
            f"active_rupture={a['excluded_active_rupture']}, "
            f"invalid_latest={a['excluded_invalid_latest']}, no_prior={a['excluded_no_prior']}"
        )
        if a["retained_old_price_active_station_ids"]:
            ids = ", ".join(x["station_id"] for x in a["retained_old_price_active_station_ids"][:20])
            suffix = " ..." if len(a["retained_old_price_active_station_ids"]) > 20 else ""
            print(f"  old price / active station IDs: {ids}{suffix}")
        if a["excluded_inactive_station_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_inactive_station_ids"][:20])
            suffix = " ..." if len(a["excluded_inactive_station_ids"]) > 20 else ""
            print(f"  inactive station IDs: {ids}{suffix}")
        if a["excluded_active_rupture_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_active_rupture_ids"][:20])
            suffix = " ..." if len(a["excluded_active_rupture_ids"]) > 20 else ""
            print(f"  active rupture IDs: {ids}{suffix}")
        if a["excluded_invalid_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_invalid_ids"])
            print(f"  invalid latest IDs: {ids}")


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
