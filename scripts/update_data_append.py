#!/usr/bin/env python3
"""Append new official daily observations to the published data.json without rewriting history.

Design principle:
- every already-published daily point is immutable;
- only dates strictly newer than the current last daily date are appended;
- stored weekly/monthly values before the first affected bucket are immutable;
- the week/month containing the first newly appended day is recalculated from the combined
  published+new daily series, because it was previously incomplete.

This makes weekly automation reproducible even if the upstream annual stock later receives
historical corrections.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

ORIGIN = core.ORIGIN
SERIES = ["corse", "moy_regions"] + core.REGIONS


def r3(values):
    return round(sum(values) / len(values) + 1e-12, 3) if values else None


def monday_offset(off: int) -> int:
    d = ORIGIN + timedelta(days=off)
    monday = d - timedelta(days=d.weekday())
    return (monday - ORIGIN).days


def month_key(off: int) -> str:
    d = ORIGIN + timedelta(days=off)
    return f"{d.year:04d}-{d.month:02d}"


def rebuild_weekly_from(points, first_week: int):
    buckets = defaultdict(lambda: [[], []])
    for off, ttc, ht in points:
        wk = monday_offset(off)
        if wk < first_week:
            continue
        if ttc is not None:
            buckets[wk][0].append(ttc)
        if ht is not None:
            buckets[wk][1].append(ht)
    return [[wk, r3(vals[0]), r3(vals[1])] for wk, vals in sorted(buckets.items())]


def rebuild_monthly_from(points, first_month: str):
    buckets = defaultdict(lambda: [[], []])
    for off, ttc, ht in points:
        mk = month_key(off)
        if mk < first_month:
            continue
        if ttc is not None:
            buckets[mk][0].append(ttc)
        if ht is not None:
            buckets[mk][1].append(ht)
    return [[mk, r3(vals[0]), r3(vals[1])] for mk, vals in sorted(buckets.items())]


def validate_shape(data: dict):
    if data.get("origin") != str(ORIGIN):
        raise RuntimeError(f"Unexpected origin: {data.get('origin')!r}")
    last_offsets = set()
    for fuel in ("G", "S"):
        for name in SERIES:
            pts = data[fuel][name]["d"]
            if not pts:
                raise RuntimeError(f"Empty daily series: {fuel}/{name}")
            offs = [p[0] for p in pts]
            if offs != sorted(offs) or len(offs) != len(set(offs)):
                raise RuntimeError(f"Daily offsets are not strictly unique/sorted: {fuel}/{name}")
            last_offsets.add(offs[-1])
    if len(last_offsets) != 1:
        raise RuntimeError(f"Published daily series do not share one cutoff: {sorted(last_offsets)}")
    return next(iter(last_offsets))


def append_data(old: dict, generated: dict):
    old_cutoff = validate_shape(old)
    cutoff_date = ORIGIN + timedelta(days=old_cutoff)
    first_new = old_cutoff + 1
    first_week = monday_offset(first_new)
    first_month = month_key(first_new)

    out = json.loads(json.dumps(old))
    appended_counts = []

    for fuel in ("G", "S"):
        for name in SERIES:
            old_daily = old[fuel][name]["d"]
            generated_daily = generated[fuel][name]["d"]
            new_daily = [p for p in generated_daily if p[0] > old_cutoff]
            if not new_daily:
                raise RuntimeError(f"No new daily data found for {fuel}/{name} after {cutoff_date}")

            candidate_daily = old_daily + new_daily
            offs = [p[0] for p in candidate_daily]
            if offs != sorted(offs) or len(offs) != len(set(offs)):
                raise RuntimeError(f"Append created duplicate/out-of-order offsets: {fuel}/{name}")

            # Prove published daily history is byte-for-value unchanged.
            if candidate_daily[:len(old_daily)] != old_daily:
                raise RuntimeError(f"Published daily history changed unexpectedly: {fuel}/{name}")

            out[fuel][name]["d"] = candidate_daily

            # Preserve every fully historical aggregate. Rebuild only the bucket containing
            # the first new day and all later buckets.
            old_w = [p for p in old[fuel][name]["w"] if p[0] < first_week]
            new_w = rebuild_weekly_from(candidate_daily, first_week)
            out[fuel][name]["w"] = old_w + new_w

            old_m = [p for p in old[fuel][name]["m"] if p[0] < first_month]
            new_m = rebuild_monthly_from(candidate_daily, first_month)
            out[fuel][name]["m"] = old_m + new_m

            appended_counts.append((fuel, name, len(new_daily), new_daily[-1][0]))

    end_offsets = {x[3] for x in appended_counts}
    if len(end_offsets) != 1:
        raise RuntimeError(f"Generated series end on different dates: {sorted(end_offsets)}")
    end_off = next(iter(end_offsets))
    end_date = ORIGIN + timedelta(days=end_off)

    print(f"Published history frozen through {cutoff_date}")
    print(f"Appended {end_off-old_cutoff} new calendar days: {cutoff_date + timedelta(days=1)} -> {end_date}")
    print(f"Rebuilt aggregates from week {ORIGIN + timedelta(days=first_week)} and month {first_month}")
    return out, old_cutoff, end_off


def verify_immutability(old: dict, candidate: dict, old_cutoff: int):
    for fuel in ("G", "S"):
        for name in SERIES:
            old_d = old[fuel][name]["d"]
            cand_d = candidate[fuel][name]["d"]
            if cand_d[:len(old_d)] != old_d:
                raise RuntimeError(f"IMMUTABILITY FAILURE {fuel}/{name}")
            if cand_d[len(old_d)][0] != old_cutoff + 1:
                raise RuntimeError(f"Missing first new day for {fuel}/{name}")
    print("Immutability check: OK — every published daily point is unchanged")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data.json")
    ap.add_argument("--output", default="data-candidate.json")
    ap.add_argument("--year", type=int, default=date.today().year)
    args = ap.parse_args()

    old = json.loads(Path(args.input).read_text(encoding="utf-8"))
    generated = core.payload(core.build_daily(args.year))
    candidate, old_cutoff, end_off = append_data(old, generated)
    verify_immutability(old, candidate, old_cutoff)

    Path(args.output).write_text(
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote candidate {args.output} ({Path(args.output).stat().st_size:,} bytes)")
    print(f"Candidate last date: {ORIGIN + timedelta(days=end_off)}")

if __name__ == "__main__":
    main()
