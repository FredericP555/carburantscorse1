#!/usr/bin/env python3
"""Detect an economically constraining TotalEnergies ceiling in Corsica.

Historical yellow zones already published by the dashboard are frozen. They are not
reconstructed: the recovered June-2026 working files show that historical classification was
not reducible to one mechanical threshold.

Prospective rule, used only after 28 May 2026:
1. the commercial ceiling applicable to the fuel is known explicitly;
2. at least 20% of active TotalEnergies stations are within 1.5 c/L below that ceiling;
3. the 75th percentile of active non-Total Corsica stations is at or above the ceiling,
   providing an independent signal that market pressure is high enough for the ceiling to
   plausibly constrain TotalEnergies prices;
4. inactive gaps <= 4 days are filled and isolated runs < 5 days are discarded.

This separates "many Total stations happen to display the ceiling" from "the ceiling is
actually biting while the surrounding Corsican market is pressing against/above it".
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

TOLERANCE_EUR = 0.015
MIN_TOTAL_NEAR_SHARE = 0.20
MARKET_QUANTILE = 0.75
MARKET_PRESSURE_TOLERANCE_EUR = 0.0
MAX_GAP_DAYS = 4
MIN_RUN_DAYS = 5
MAX_AGE_DAYS = core.MAX_FFILL_DAYS

REGISTRY = json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))
CURRENT_TOTAL_IDS = set(REGISTRY['stations'])
HISTORICAL_TOTAL_IDS = set(REGISTRY.get('historical_aliases', {}))
TOTAL_IDS = CURRENT_TOTAL_IDS | HISTORICAL_TOTAL_IDS

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

# Formal ceiling chronology used by the latest supplied carburantscorse1 app.js.
# The recovered June Corse/BdR project contains slightly different transition dates; that
# discrepancy is deliberately documented rather than silently blended into historical zones.
def cap_for(fuel: str, d: date) -> float | None:
    if fuel == 'SP95':
        return 1.99 if d >= date(2023,3,1) else None
    if fuel == 'Gazole':
        if date(2023,3,1) <= d <= date(2026,3,19):
            return 1.99
        if date(2026,3,20) <= d <= date(2026,4,7):
            return 2.09
        if d >= date(2026,4,8):
            return 2.25
    return None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    x = sorted(values)
    if len(x) == 1:
        return x[0]
    pos = (len(x)-1)*q
    lo = int(pos)
    hi = min(lo+1, len(x)-1)
    frac = pos-lo
    return x[lo]*(1-frac) + x[hi]*frac


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
    combined=defaultdict(list)
    for y in (year-1, year):
        for (sid,region,fuel),vals in core.parse_year(y).items():
            if region=='corse' and fuel in ('Gazole','SP95'):
                combined[(sid,fuel)].extend(vals)
    for vals in combined.values():
        vals.sort(key=lambda x:x[0])

    start=date(year,1,1)
    end=min(date(year,12,31),date.today()-timedelta(days=1))
    result={}

    for fuel in ('Gazole','SP95'):
        station_ids={sid for sid,f in combined if f==fuel}
        ptr={sid:0 for sid in station_ids}
        state={sid:None for sid in station_ids}
        raw=[]; stats={}
        d=start
        while d<=end:
            total_prices=[]; non_total_prices=[]
            for sid in station_ids:
                vals=combined.get((sid,fuel),[])
                j=ptr[sid]
                while j<len(vals) and vals[j][0].date()<=d:
                    state[sid]=vals[j]
                    j+=1
                ptr[sid]=j
                st=state[sid]
                if st is None:
                    continue
                ts,value=st
                if (d-ts.date()).days>MAX_AGE_DAYS or value is None:
                    continue
                if sid in TOTAL_IDS:
                    total_prices.append(value)
                else:
                    non_total_prices.append(value)

            cap=cap_for(fuel,d)
            if cap is not None and total_prices and non_total_prices:
                near=sum(1 for p in total_prices if cap-TOLERANCE_EUR <= p <= cap+0.0015)
                near_share=near/len(total_prices)
                market_p75=percentile(non_total_prices, MARKET_QUANTILE)
                pressure=(market_p75 is not None and market_p75 >= cap-MARKET_PRESSURE_TOLERANCE_EUR)
                raw_active=(near_share>=MIN_TOTAL_NEAR_SHARE and pressure)
                raw.append((d,raw_active))
                stats[d]={
                    'cap':cap,
                    'total_stations':len(total_prices),
                    'non_total_stations':len(non_total_prices),
                    'near_count':near,
                    'near_share':near_share,
                    'non_total_p75':market_p75,
                    'market_pressure':pressure,
                    'raw_active':raw_active,
                    'total_min_price':min(total_prices),
                    'total_max_price':max(total_prices),
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
    """Freeze published history; append only genuinely prospective detections."""
    legacy=list(LEGACY_RANGES[fuel])
    prospective=[]
    for a,b in detected[fuel]['detected_ranges']:
        if b <= FROZEN_THROUGH:
            continue
        prospective.append((max(a,FROZEN_THROUGH+timedelta(days=1)),b))
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
                if a<=latest<=b:
                    active_since=a
                    break
        s=stats.get(latest,{}) if latest else {}
        out[fuel]={
            'ranges':[{'d1':str(a),'d2':str(b)} for a,b in ranges],
            'current_active':bool(latest_flag),
            'current_active_since':str(active_since) if active_since else None,
            'current_cap':s.get('cap'),
            'latest_total_stations':s.get('total_stations'),
            'latest_non_total_stations':s.get('non_total_stations'),
            'latest_near_share':round(s.get('near_share',0),4) if s else None,
            'latest_non_total_p75':round(s.get('non_total_p75'),3) if s.get('non_total_p75') is not None else None,
            'latest_market_pressure':s.get('market_pressure'),
            'rule':{
                'near_cap_tolerance_cents':TOLERANCE_EUR*100,
                'min_total_near_share':MIN_TOTAL_NEAR_SHARE,
                'market_reference':'75e percentile des stations corses non-Total',
                'market_pressure_threshold':'>= plafond',
                'fill_gap_days':MAX_GAP_DAYS,
                'min_run_days':MIN_RUN_DAYS,
                'historical_ranges_frozen_through':str(FROZEN_THROUGH),
            },
        }
    return out

if __name__=='__main__':
    print(json.dumps(metadata(),ensure_ascii=False,indent=2))
