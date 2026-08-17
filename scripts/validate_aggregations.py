#!/usr/bin/env python3
"""Validate how well stored weekly/monthly series can be rebuilt from stored daily points.

This uses only the already-published data.json, so it tests aggregation semantics independently
from any changes in the official upstream annual stock.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ORIGIN = date(2022, 1, 1)
REGIONS = [
    "corse","moy_regions","Auvergne-Rhône-Alpes","Bourgogne-Franche-Comté","Bretagne",
    "Centre-Val de Loire","Grand Est","Hauts-de-France","Île-de-France","Normandie",
    "Nouvelle-Aquitaine","Occitanie","PACA","Pays de la Loire",
]


def r3(x):
    return round(sum(x) / len(x) + 1e-12, 3) if x else None


def rebuild_daily_to_weekly(points):
    buckets = defaultdict(lambda: [[], []])
    for off, ttc, ht in points:
        d = ORIGIN + timedelta(days=off)
        monday = d - timedelta(days=d.weekday())
        key = (monday - ORIGIN).days
        if ttc is not None: buckets[key][0].append(ttc)
        if ht is not None: buckets[key][1].append(ht)
    return [[k, r3(v[0]), r3(v[1])] for k, v in sorted(buckets.items())]


def rebuild_daily_to_monthly(points):
    buckets = defaultdict(lambda: [[], []])
    for off, ttc, ht in points:
        d = ORIGIN + timedelta(days=off)
        key = f"{d.year:04d}-{d.month:02d}"
        if ttc is not None: buckets[key][0].append(ttc)
        if ht is not None: buckets[key][1].append(ht)
    return [[k, r3(v[0]), r3(v[1])] for k, v in sorted(buckets.items())]


def compare(stored, rebuilt):
    sm = {p[0]: p[1:] for p in stored}
    rm = {p[0]: p[1:] for p in rebuilt}
    common = sorted(set(sm) & set(rm))
    diffs = []
    for k in common:
        for j in (0, 1):
            a, b = sm[k][j], rm[k][j]
            if a is not None and b is not None:
                diffs.append((abs(a-b), k, j, a, b))
    if not diffs:
        return 999, 999, None
    mae = sum(d[0] for d in diffs) / len(diffs)
    worst = max(diffs)
    return mae, worst[0], worst


def main():
    data = json.loads(Path('data.json').read_text(encoding='utf-8'))
    all_ok = True
    for fuel in ('G','S'):
        print(f"\n===== {fuel} =====")
        for region in REGIONS:
            d = data[fuel][region]['d']
            rw = rebuild_daily_to_weekly(d)
            rm = rebuild_daily_to_monthly(d)
            w_mae, w_max, w_worst = compare(data[fuel][region]['w'], rw)
            m_mae, m_max, m_worst = compare(data[fuel][region]['m'], rm)
            print(f"{region:28} W mae={w_mae*100:5.3f}c max={w_max*100:5.3f}c | M mae={m_mae*100:5.3f}c max={m_max*100:5.3f}c")
            if w_max > 0.003 or m_max > 0.003:
                all_ok = False
                print('  worst W:', w_worst)
                print('  worst M:', m_worst)
    print('\nAggregation reconstruction:', 'GOOD' if all_ok else 'DIFFERENCES FOUND')

if __name__ == '__main__':
    main()
