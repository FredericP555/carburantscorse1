#!/usr/bin/env python3
"""Independently verify and optionally promote the C1 V2 candidate.

The builder never writes data.json. This guard checks the transition boundaries again
before promotion. On recurring runs all already-published daily rows are immutable;
weekly/monthly aggregates may only be rebuilt from the bucket containing the first newly
appended daily date.

P1 hardening also refreshes metadata derived from the actual candidate cutoff, then applies
an independent fail-closed contract to the newly appended public tail.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

import c1_bouclier_meta
import c1_last_date
import c1_v2_contracts
import update_data_v2 as core

ROOT = Path(__file__).resolve().parents[1]
DAILY_SWITCH = date(2026, 7, 23)
WEEKLY_SWITCH = date(2026, 7, 27)
MONTHLY_SWITCH = "2026-08"


def _week_offset(day: date) -> int:
    monday = day - timedelta(days=day.weekday())
    return (monday - core.ORIGIN).days


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _validate_order(name: str, rows: list[list], granularity: str) -> None:
    keys = [row[0] for row in rows]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise SystemExit(f"Refusing C1 V2 candidate: invalid ordering in {name}/{granularity}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", default="outputs/c1-v2-candidate.json")
    p.add_argument("--summary", default="outputs/c1-v2-summary.json")
    p.add_argument("--target", default="data.json")
    p.add_argument("--promote", action="store_true")
    args = p.parse_args()

    candidate_path = ROOT / args.candidate
    summary_path = ROOT / args.summary
    target_path = ROOT / args.target
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    baseline = json.loads(target_path.read_text(encoding="utf-8"))

    # Canonicalize only metadata that is derived from the candidate itself.  This is done
    # before validation so downstream bundle generation sees exactly the guarded metadata.
    try:
        candidate, summary = c1_v2_contracts.refresh_publication_metadata(
            candidate, baseline, summary
        )
        c1_v2_contracts.validate_all(baseline, candidate)
    except ValueError as exc:
        raise SystemExit(f"Refusing C1 V2 candidate: {exc}") from exc
    candidate_path.write_text(
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    v2 = ((candidate.get("meta") or {}).get("v2") or {})
    baseline_v2 = ((baseline.get("meta") or {}).get("v2") or {})
    initial = not bool(baseline_v2.get("active"))
    if not v2.get("active"):
        raise SystemExit("Refusing C1 V2 candidate: activation metadata absent")
    if v2.get("daily_switch_date") != DAILY_SWITCH.isoformat():
        raise SystemExit("Refusing C1 V2 candidate: invalid daily transition date")
    if v2.get("weekly_switch_date") != WEEKLY_SWITCH.isoformat():
        raise SystemExit("Refusing C1 V2 candidate: invalid weekly transition date")
    if v2.get("monthly_switch") != MONTHLY_SWITCH:
        raise SystemExit("Refusing C1 V2 candidate: invalid monthly transition")
    if int((summary.get("engine") or {}).get("r2", {}).get("unavailable", 0)) != 0:
        raise SystemExit("Refusing C1 V2 candidate: R2 unavailable")
    source_max = str((summary.get("engine") or {}).get("source_max_date") or "")
    target_end = str(summary.get("target_end") or "")
    if not source_max or not target_end or target_end > source_max:
        raise SystemExit(f"Refusing C1 V2 candidate: target_end={target_end} source_max={source_max}")

    try:
        c1_bouclier_meta.validate_detector_bouclier(
            candidate.get("meta") or {},
            (summary.get("engine") or {}).get("bouclier"),
        )
    except ValueError as exc:
        raise SystemExit(f"Refusing C1 V2 candidate: {exc}") from exc

    try:
        c1_last_date.validate_last_date(candidate)
    except ValueError as exc:
        raise SystemExit(f"Refusing C1 V2 candidate: {exc}") from exc

    first_new_day: date | None = None
    for fuel in ("G", "S"):
        old_daily = baseline[fuel]["corse"]["d"]
        new_daily = candidate[fuel]["corse"]["d"]
        if len(new_daily) > len(old_daily):
            d = core.ORIGIN + timedelta(days=old_daily[-1][0] + 1)
            first_new_day = d if first_new_day is None or d < first_new_day else first_new_day

    protected = 0
    for fuel in ("G", "S"):
        if set(baseline[fuel]) != set(candidate[fuel]):
            raise SystemExit(f"Refusing C1 V2 candidate: region topology changed for {fuel}")
        for region in baseline[fuel]:
            for gran in ("d", "w", "m"):
                old = baseline[fuel][region][gran]
                new = candidate[fuel][region][gran]
                _validate_order(f"{fuel}/{region}", new, gran)
                if initial:
                    if gran == "d":
                        boundary = (DAILY_SWITCH - core.ORIGIN).days
                    elif gran == "w":
                        boundary = (WEEKLY_SWITCH - core.ORIGIN).days
                    else:
                        boundary = MONTHLY_SWITCH
                else:
                    if gran == "d":
                        # Every daily row already published before this run is immutable.
                        if new[:len(old)] != old:
                            raise SystemExit(f"Refusing C1 V2 candidate: daily history rewritten in {fuel}/{region}")
                        protected += len(old)
                        continue
                    if first_new_day is None:
                        if new != old:
                            raise SystemExit(f"Refusing C1 V2 candidate: no-new-data run changed {fuel}/{region}/{gran}")
                        protected += len(old)
                        continue
                    boundary = _week_offset(first_new_day) if gran == "w" else _month_key(first_new_day)

                old_prefix = [row for row in old if row[0] < boundary]
                new_prefix = [row for row in new if row[0] < boundary]
                if old_prefix != new_prefix:
                    raise SystemExit(f"Refusing C1 V2 candidate: protected history changed in {fuel}/{region}/{gran}")
                protected += len(old_prefix)

    if initial and int(summary.get("rewritten_daily_rows_total", 0)) <= 0:
        raise SystemExit("Refusing C1 V2 candidate: initial transition rewrote no daily rows")
    if not initial and int(summary.get("rewritten_daily_rows_total", 0)) != 0:
        raise SystemExit("Refusing C1 V2 candidate: recurring run attempted daily rewrites")

    result = {
        "status": "C1 V2 candidate verified",
        "initial_transition": initial,
        "protected_rows_verified": protected,
        "rewritten_daily_rows": summary.get("rewritten_daily_rows_total", 0),
        "added_daily_rows": summary.get("added_daily_rows_total", 0),
        "target_end": target_end,
        "production_modified": bool(args.promote),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.promote:
        target_path.write_text(candidate_path.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()
