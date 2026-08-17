#!/usr/bin/env python3
"""Production detector for an economically effective TotalEnergies price ceiling in Corsica.

Transparent rule calibrated against the dashboard's historical yellow zones:
- at least 30% of active TotalEnergies Corsica stations are within 1.5 c/L below the cap;
- fill inactive gaps of at most 4 consecutive days when bounded by active days;
- discard isolated active runs shorter than 7 days.

The 4-day gap was chosen over the tied 5-day rule because it achieves the same historical
calibration score while being more conservative.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

TOLERANCE_EUR = 0.015
MIN_SHARE = 0.30
MAX_GAP_DAYS = 4
MIN_RUN_DAYS = 7
MAX_AGE_DAYS = core.MAX_FFILL_DAYS
TOTAL_IDS = set(json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))['stations'])

# Existing dashboard history is frozen through this date. Detection is used prospectively
# after it; old yellow zones are never silently rewritten.
FROZEN_THROUGH = date(2026, 5, 28)

LEGACY_RANGES = {
    'Gazole': [
        (date(2023,8,31),date(2023,10,13)),
        (date(2023,10,24),date(2023,10,30)),
        (date(2026,3,20),date(2026,4,6)),
        (date(2026,4,8),date(2026,5,27)),
    ],
    'SP95': [
        (date(2023,2,20),date(2023,3,19)),
        (date(2023,3,27),date(2023,5,2)),
        (date(2023,6,9),date(2023,6,21)),
        (date(2023,7,25),date(2023,10,7)),
        (date(2024,2,20),date(2024,3,1)),
        (date(2024,3,7),date(2024,6,5)),
        (date(2024,7,1),date(2024,7,16)),
        (date(2026,3,13),date(2026,5,28)),
    ],
}


def cap_for(fuel: str, d: date) -> float | None:
    """Known commercial ceilings relevant to the dashboard.

    This is the one exceptional configuration that must be updated if TotalEnergies changes
    the announced ceiling. It is deliberately explicit rather than inferred from prices.
    """
    if fuel == 'SP95':
        return 1.99 if d >= date(2023,2,1) else None
    if fuel == 'Gazole':
        if date(2023,2,1) <= d <= date(2026,3,11):
            return 1.99
        if date(2026,3,12) <= d <= date(2026,4,7):
            return 2.09
        if d >= date(2026,4,8):
            return 2.25
    return None


def _stable_flags(items: list[tuple[date,bool]]) -> list[tuple[date,bool]]:
    vals=[[d,b] for d,b in sorted(items)]
    i=0
    while i < len(vals):
        if vals[i][1]:
            i += 1; continue
        j=i
        while j < len(vals) and not vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)):
            j += 1
        gap=j-i
        left=i>0 and vals[i-1][1] and vals[i][0]==vals[i-1][0]+timedelta(days=1)
        right=j<len(vals) and vals[j][1] and vals[j][0]==vals[j-1][0]+timedelta(days=1)
        if left and right and gap <= MAX_GAP_DAYS:
            for k in range(i,j): vals[k][1]=True
        i=j

    i=0
    while i < len(vals):
        if not vals[i][1]:
            i += 1; continue
        j=i
        while j < len(vals) and vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)):
            j += 1
        if j-i < MIN_RUN_DAYS:
            for k in range(i,j): vals[k][1]=False
        i=j
    return [(d,b) for d,b in vals]


def _ranges(flags: list[tuple[date,bool]]) -> list[tuple[date,date]]:
    out=[]; start=None; prev=None
    for d,b in flags:
        if b and start is None: start=d
        if start is not None and (not b or (prev is not None and d != prev+timedelta(days=1))):
            out.append((start,prev)); start=d if b else None
        prev=d
    if start is not None: out.append((start,prev))
    return out


def _merge_ranges(ranges: list[tuple[date,date]]) -> list[tuple[date,date]]:
    if not ranges: return []
    out=[]
    for a,b in sorted(ranges):
        if not out or a > out[-1][1] + timedelta(days=1):
            out.append([a,b])
        else:
            out[-1][1]=max(out[-1][1],b)
    return [(a,b) for a,b in out]


def detect_year(year: int | None = None) -> dict:
    year=year or date.today().year
    parsed=core.parse_year(year)
    updates={}
    for (sid,region,fuel),vals in parsed.items():
        if region=='corse' and sid in TOTAL_IDS and fuel in ('Gazole','SP95'):
            vals.sort(key=lambda x:x[0]); updates[(sid,fuel)]=vals

    start=date(year,1,1)
    end=min(date(year,12,31),date.today()-timedelta(days=1))
    result={}
    for fuel in ('Gazole','SP95'):
        ptr={sid:0 for sid in TOTAL_IDS}; state={sid:None for sid in TOTAL_IDS}
        raw=[]; stats={}
        d=start
        while d<=end:
            prices=[]
            for sid in TOTAL_IDS:
                vals=updates.get((sid,fuel),[]); j=ptr[sid]
                while j<len(vals) and vals[j][0].date()<=d:
                    state[sid]=vals[j]; j+=1
                ptr[sid]=j
                st=state[sid]
                if st is not None and (d-st[0].date()).days<=MAX_AGE_DAYS:
                    prices.append(st[1])
            cap=cap_for(fuel,d)
            if cap is not None and prices:
                near=sum(1 for p in prices if cap-TOLERANCE_EUR <= p <= cap+0.0015)
                share=near/len(prices)
                raw.append((d,share>=MIN_SHARE))
                stats[d]={
                    'cap':cap,'stations':len(prices),'near_count':near,'near_share':share,
                    'min_price':min(prices),'max_price':max(prices),
                }
            d += timedelta(days=1)
        stable=_stable_flags(raw)
        result[fuel]={
            'flags':dict(stable),
            'detected_ranges':_ranges(stable),
            'stats':stats,
        }
    return result


def display_ranges(fuel: str, detected: dict) -> list[tuple[date,date]]:
    """Freeze all previously published yellow history, append only prospective detection."""
    legacy=list(LEGACY_RANGES[fuel])
    prospective=[]
    for a,b in detected[fuel]['detected_ranges']:
        if b <= FROZEN_THROUGH: continue
        a=max(a,FROZEN_THROUGH+timedelta(days=1))
        prospective.append((a,b))
    return _merge_ranges(legacy+prospective)


def metadata(year: int | None = None) -> dict:
    det=detect_year(year)
    out={}
    for fuel in ('Gazole','SP95'):
        ranges=display_ranges(fuel,det)
        stats=det[fuel]['stats']
        latest=max(stats) if stats else None
        latest_flag=det[fuel]['flags'].get(latest,False) if latest else False
        active_since=None
        if latest_flag:
            for a,b in det[fuel]['detected_ranges']:
                if a<=latest<=b: active_since=a
        s=stats.get(latest,{}) if latest else {}
        out[fuel]={
            'ranges':[{'d1':str(a),'d2':str(b)} for a,b in ranges],
            'current_active':bool(latest_flag),
            'current_active_since':str(active_since) if active_since else None,
            'current_cap':s.get('cap'),
            'latest_total_stations':s.get('stations'),
            'latest_near_share':round(s.get('near_share',0),4) if s else None,
            'rule':{
                'near_cap_tolerance_cents':TOLERANCE_EUR*100,
                'min_share':MIN_SHARE,
                'fill_gap_days':MAX_GAP_DAYS,
                'min_run_days':MIN_RUN_DAYS,
            },
        }
    return out

if __name__=='__main__':
    print(json.dumps(metadata(),ensure_ascii=False,indent=2))
