#!/usr/bin/env python3
"""Add dynamic date, bouclier and editorial metadata to data.json.

Recovered historical rule for the editorial indicator "hors toute action TotalEnergies":
a day is excluded from the structural average whenever a TotalEnergies intervention is active
on EITHER Gazole OR SP95. The action calendar is therefore the UNION of the two fuel-specific
bouclier/intervention calendars, not the calendar of the fuel currently analysed.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import statistics

import bouclier_detector as bd
import update_data_v2 as core

ORIGIN=core.ORIGIN


def ranges_as_dates(items):
    return [(date.fromisoformat(x['d1']),date.fromisoformat(x['d2'])) for x in items]


def merge_ranges(ranges):
    """Merge overlapping/adjacent date ranges."""
    if not ranges:
        return []
    out=[]
    for a,b in sorted(ranges):
        if not out or a > out[-1][1] + timedelta(days=1):
            out.append([a,b])
        else:
            out[-1][1]=max(out[-1][1],b)
    return [(a,b) for a,b in out]


def total_action_ranges(bmeta:dict, year:int):
    """Union of all TotalEnergies action periods across Gazole and SP95 for one year.

    This is the rule recovered from the historical dashboard: "hors toute action" means that
    a date is excluded for BOTH fuel analyses if an intervention is active on at least one fuel.
    """
    ranges=[]
    for fuel in ('Gazole','SP95'):
        ranges.extend(ranges_as_dates(bmeta[fuel]['ranges']))
    merged=merge_ranges(ranges)
    start=date(year,1,1); end=date(year,12,31)
    return [(max(a,start),min(b,end)) for a,b in merged if b>=start and a<=end]


def inside(d,ranges):
    return any(a<=d<=b for a,b in ranges)


# Use the verified historical TotalEnergies action calendar until 2025;
# completed years from 2026 use the effective bouclier calendar.
REMISES_2022 = [(date(2022, 9, 1), date(2022, 12, 31))]


def editorial_calendar_for_year(bmeta: dict, year: int):
    if year >= bd.DYNAMIC_START_YEAR:
        return total_action_ranges(bmeta, year)
    ranges = list(REMISES_2022)
    for fuel in ('Gazole', 'SP95'):
        ranges.extend(bd.LEGACY_RANGES[fuel])
    start, end = date(year, 1, 1), date(year, 12, 31)
    return [(max(a, start), min(b, end))
            for a, b in merge_ranges(ranges) if a <= end and b >= start]


def paired_daily_gaps(data: dict, short: str):
    corse = {p[0]: p[2] for p in data[short]['corse']['d']}
    mainland = {p[0]: p[2] for p in data[short]['moy_regions']['d']}
    return sorted(
        (ORIGIN + timedelta(days=off), (ht - mainland[off]) * 100)
        for off, ht in corse.items()
        if ht is not None and mainland.get(off) is not None
    )


def completed_annual_gaps(data: dict, short: str, year: int, bmeta: dict):
    rows = paired_daily_gaps(data, short)
    results = []
    for completed_year in range(ORIGIN.year, year):
        yearly = [(day, gap) for day, gap in rows if day.year == completed_year]
        if not yearly:
            continue
        calendar = editorial_calendar_for_year(bmeta, completed_year)
        outside = [gap for day, gap in yearly if not inside(day, calendar)]
        observed = [gap for _, gap in yearly]
        results.append({
            'year': completed_year,
            'observed_gap': round(statistics.fmean(observed), 1),
            'outside_total_action_gap': round(statistics.fmean(outside), 1) if outside else None,
            'outside_total_action_days': len(outside),
            'observed_days': len(observed),
        })
    return results


def completed_week_comparison(data: dict, short: str, last_day: date):
    """Compare only two complete Monday-Sunday weeks of paired daily HT gaps."""
    last_sunday = last_day - timedelta(days=(last_day.weekday() + 1) % 7)
    latest_start = last_sunday - timedelta(days=6)
    previous_start = latest_start - timedelta(days=7)
    by_day = dict(paired_daily_gaps(data, short))

    def whole_week(start):
        dates = [start + timedelta(days=i) for i in range(7)]
        return [by_day[d] for d in dates] if all(d in by_day for d in dates) else None

    latest, previous = whole_week(latest_start), whole_week(previous_start)
    if latest is None or previous is None:
        return None
    latest_gap = round(statistics.fmean(latest), 1)
    previous_gap = round(statistics.fmean(previous), 1)
    return {
        'latest_start': str(latest_start),
        'latest_end': str(last_sunday),
        'latest_gap': latest_gap,
        'previous_gap': previous_gap,
        'change': round(latest_gap - previous_gap, 1),
    }


def editorial_for(data:dict, short:str, fuel_name:str, fuel_bmeta:dict, year:int, action_ranges, bmeta:dict):
    corse={p[0]:p[2] for p in data[short]['corse']['d']}
    mainland={p[0]:p[2] for p in data[short]['moy_regions']['d']}
    rows=[]
    for off,hc in corse.items():
        hm=mainland.get(off)
        if hc is None or hm is None:
            continue
        d=ORIGIN+timedelta(days=off)
        if d.year!=year:
            continue
        rows.append((d,(hc-hm)*100))
    if not rows:
        return None

    observed=[v for _,v in rows]
    outside=[v for d,v in rows if not inside(d,action_ranges)]
    during=[v for d,v in rows if inside(d,action_ranges)]

    def a(xs):
        return round(statistics.fmean(xs),1) if xs else None

    return {
        'year':year,
        'through':str(rows[-1][0]),
        'observed_ytd_gap':a(observed),
        'outside_total_action_gap':a(outside),
        'during_total_action_gap':a(during),
        'total_action_days':len(during),
        'outside_total_action_days':len(outside),
        'total_action_ranges_used':[{'d1':str(a),'d2':str(b)} for a,b in action_ranges],
        'historical_annual':completed_annual_gaps(data, short, year, bmeta),
        'weekly_change':completed_week_comparison(data, short, rows[-1][0]),
        # Fuel-specific current status remains useful for the graph/legend.
        'current_active':fuel_bmeta['current_active'],
        'current_active_since':fuel_bmeta['current_active_since'],
        'current_cap':fuel_bmeta['current_cap'],
        'latest_total_stations':fuel_bmeta['latest_total_stations'],
        'latest_near_share':fuel_bmeta['latest_near_share'],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default='data-candidate.json')
    ap.add_argument('--output',default=None)
    args=ap.parse_args()
    path=Path(args.input); outpath=Path(args.output or args.input)
    data=json.loads(path.read_text(encoding='utf-8'))
    existing_station_audit=(data.get('meta') or {}).get('station_audit')

    last_off=max(p[0] for p in data['G']['corse']['d'])
    last_date=ORIGIN+timedelta(days=last_off)
    year=last_date.year
    bmeta=bd.metadata(year)
    action_ranges=total_action_ranges(bmeta,year)

    meta={
        'last_date':str(last_date),
        'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'update_policy':'append-only',
        'editorial_action_rule':'union-of-gazole-and-sp95-total-intervention-periods',
        'bouclier':bmeta,
        'editorial':{
            'Gazole':editorial_for(data,'G','Gazole',bmeta['Gazole'],year,action_ranges,bmeta),
            'SP95':editorial_for(data,'S','SP95',bmeta['SP95'],year,action_ranges,bmeta),
        },
    }
    if existing_station_audit is not None:
        meta['station_audit']=existing_station_audit

    data['meta']=meta
    outpath.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    print('Wrote',outpath)

if __name__=='__main__':
    main()
