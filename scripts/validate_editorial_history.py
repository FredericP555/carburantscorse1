#!/usr/bin/env python3
"""Prove the recovered historical 'hors toute action TotalEnergies' calculation.

Recovered rule:
- compute the daily HT gap Corse - equal-weight mean of the 12 metropolitan regions;
- classify a day as 'action TotalEnergies' if ANY Total intervention is active on EITHER
  Gazole OR SP95 (plus the 2022 fuel discounts);
- average the daily gaps inside/outside that UNION of dates.

The expected values below are the figures hard-coded in the historical dashboard.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, timedelta
from pathlib import Path

import bouclier_detector as bd

ORIGIN=date(2022,1,1)
HISTORICAL_CUTOFF=date(2026,5,28)
REMISES_2022=[(date(2022,9,1),date(2022,12,31))]

EXPECTED_ANNUAL={
    'G':{2022:15.3,2023:17.3,2024:18.1,2025:18.3},
    'S':{2022:14.2,2023:14.3,2024:17.2,2025:17.3},
}
EXPECTED_GLOBAL={
    'G':{'outside':17.2,'during':13.1},
    'S':{'outside':16.0,'during':10.2},
}
EXPECTED_PRE_ACTION_2026={'G':15.3,'S':16.4}


def merge_ranges(ranges):
    out=[]
    for a,b in sorted(ranges):
        if not out or a>out[-1][1]+timedelta(days=1):
            out.append([a,b])
        else:
            out[-1][1]=max(out[-1][1],b)
    return [(a,b) for a,b in out]


def inside(d,ranges):
    return any(a<=d<=b for a,b in ranges)


def daily_gap(data,fuel):
    c={p[0]:p[2] for p in data[fuel]['corse']['d']}
    m={p[0]:p[2] for p in data[fuel]['moy_regions']['d']}
    return [(ORIGIN+timedelta(days=off),(hc-m[off])*100)
            for off,hc in c.items() if hc is not None and m.get(off) is not None]


def r1(values):
    return round(statistics.fmean(values)+1e-12,1)


def main():
    data=json.loads(Path('data.json').read_text(encoding='utf-8'))

    # Historical editorial classification = union across BOTH fuels, not fuel-specific ranges.
    action_ranges=merge_ranges(
        REMISES_2022 +
        list(bd.LEGACY_RANGES['Gazole']) +
        list(bd.LEGACY_RANGES['SP95'])
    )

    print('Historical Total-action union:')
    for a,b in action_ranges:
        print(' ',a,'->',b)

    for fuel in ('G','S'):
        rows=daily_gap(data,fuel)
        print(f'\n{fuel}:')

        for year,expected in EXPECTED_ANNUAL[fuel].items():
            vals=[v for d,v in rows if d.year==year and not inside(d,action_ranges)]
            got=r1(vals)
            print(f' {year} hors toute action: {got:.1f} c/L (expected {expected:.1f})')
            assert got==expected, f'{fuel} {year}: got {got}, expected {expected}'

        before=[v for d,v in rows if date(2026,1,1)<=d<=date(2026,3,12)]
        got_pre=r1(before)
        exp_pre=EXPECTED_PRE_ACTION_2026[fuel]
        print(f' 2026 before first action (1 Jan-12 Mar): {got_pre:.1f} c/L (expected {exp_pre:.1f})')
        assert got_pre==exp_pre, f'{fuel} pre-action 2026: got {got_pre}, expected {exp_pre}'

        hist=[(d,v) for d,v in rows if d<=HISTORICAL_CUTOFF]
        outside=[v for d,v in hist if not inside(d,action_ranges)]
        during=[v for d,v in hist if inside(d,action_ranges)]
        got_out=r1(outside); got_during=r1(during)
        exp=EXPECTED_GLOBAL[fuel]
        print(f' global through {HISTORICAL_CUTOFF}: outside={got_out:.1f}, during={got_during:.1f}')
        assert got_out==exp['outside'], f'{fuel} global outside: got {got_out}, expected {exp["outside"]}'
        assert got_during==exp['during'], f'{fuel} global during: got {got_during}, expected {exp["during"]}'

    print('\nHISTORICAL EDITORIAL METHOD: EXACTLY REPRODUCED')

if __name__=='__main__':
    main()
