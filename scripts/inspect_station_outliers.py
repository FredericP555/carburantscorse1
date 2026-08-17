#!/usr/bin/env python3
"""Inspect station-level Gazole values on dates where rebuilt regional means differ most.

This is diagnostic only. It helps recover the six anomalous observations documented
in the existing dashboard methodology without changing the public data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import statistics

import update_data_v2 as u

CASES = [
    ("Centre-Val de Loire", date(2026, 1, 1), 1.591),
    ("Centre-Val de Loire", date(2026, 2, 20), 1.674),
    ("Bretagne", date(2026, 4, 7), 2.281),
    ("Île-de-France", date(2026, 3, 3), 1.840),
    ("corse", date(2026, 3, 30), 2.211),
]


def combined_changes():
    out = defaultdict(list)
    for y in (2025, 2026):
        for k, vals in u.parse_year(y).items():
            out[k].extend(vals)
    for vals in out.values():
        vals.sort(key=lambda x: x[0])
    return out


def station_values(changes, region: str, d: date):
    vals = []
    for (sid, reg, fuel), updates in changes.items():
        if reg != region or fuel != "Gazole":
            continue
        last = None
        for ts, value in updates:
            if ts.date() <= d:
                last = (ts, value)
            else:
                break
        if last is None:
            continue
        ts, value = last
        age = (d - ts.date()).days
        if age > u.MAX_FFILL_DAYS:
            continue
        vals.append((sid, value, ts, age))
    return vals


def percentile(xs, q):
    ys = sorted(xs)
    if not ys:
        return float('nan')
    pos = (len(ys)-1)*q
    lo = int(pos)
    hi = min(lo+1, len(ys)-1)
    frac = pos-lo
    return ys[lo]*(1-frac)+ys[hi]*frac


def show_case(changes, region, d, old_target):
    rows = station_values(changes, region, d)
    xs = [r[1] for r in rows]
    mean = statistics.fmean(xs)
    med = statistics.median(xs)
    print(f"\n=== {region} {d} ===")
    print(f"n={len(xs)} rebuilt={mean:.4f} old_target={old_target:.4f} delta={mean-old_target:+.4f}")
    print(
        "min={:.3f} p1={:.3f} p5={:.3f} median={:.3f} p95={:.3f} p99={:.3f} max={:.3f}".format(
            min(xs), percentile(xs,.01), percentile(xs,.05), med,
            percentile(xs,.95), percentile(xs,.99), max(xs)
        )
    )

    # Show how robust trimming changes the mean; this helps tell genuine market spread
    # from isolated suspicious records.
    for radius in (0.10, 0.15, 0.20, 0.30, 0.50):
        kept = [x for x in xs if abs(x-med) <= radius]
        if kept:
            print(f"  median±{radius:.2f}: n={len(kept):4d} mean={statistics.fmean(kept):.4f} removed={len(xs)-len(kept)}")

    print("  lowest 15 stations:")
    for sid, value, ts, age in sorted(rows, key=lambda r:r[1])[:15]:
        print(f"    {sid}  {value:.3f}  last={ts.isoformat(sep=' ')} age={age}d  dev_med={value-med:+.3f}")
    print("  highest 15 stations:")
    for sid, value, ts, age in sorted(rows, key=lambda r:r[1], reverse=True)[:15]:
        print(f"    {sid}  {value:.3f}  last={ts.isoformat(sep=' ')} age={age}d  dev_med={value-med:+.3f}")

    # Influence of removing one station: rank stations that move the mean toward old target most.
    candidates=[]
    n=len(xs)
    total=sum(xs)
    base_err=abs(mean-old_target)
    for sid,value,ts,age in rows:
        if n <= 1:
            continue
        m2=(total-value)/(n-1)
        improvement=base_err-abs(m2-old_target)
        candidates.append((improvement,sid,value,ts,age,m2))
    print("  single-station removals that best move mean toward old target:")
    for imp,sid,value,ts,age,m2 in sorted(candidates, reverse=True)[:12]:
        print(f"    {sid} value={value:.3f} -> mean={m2:.4f} improvement={imp:.4f} age={age}d last={ts.isoformat(sep=' ')}")


def main():
    changes=combined_changes()
    for case in CASES:
        show_case(changes,*case)

if __name__ == '__main__':
    main()
