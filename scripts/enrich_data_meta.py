#!/usr/bin/env python3
"""Add dynamic date, effective-bouclier and current-year editorial metadata to data.json."""
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


def inside(d,ranges): return any(a<=d<=b for a,b in ranges)


def editorial_for(data:dict, short:str, fuel_name:str, bmeta:dict, year:int):
    corse={p[0]:p[2] for p in data[short]['corse']['d']}
    mainland={p[0]:p[2] for p in data[short]['moy_regions']['d']}
    ranges=ranges_as_dates(bmeta['ranges'])
    rows=[]
    for off,hc in corse.items():
        hm=mainland.get(off)
        if hc is None or hm is None: continue
        d=ORIGIN+timedelta(days=off)
        if d.year!=year: continue
        rows.append((d,(hc-hm)*100))
    if not rows: return None
    vals=[v for _,v in rows]
    inactive=[v for d,v in rows if not inside(d,ranges)]
    active=[v for d,v in rows if inside(d,ranges)]
    def a(xs): return round(statistics.fmean(xs),1) if xs else None
    return {
        'year':year,
        'through':str(rows[-1][0]),
        'observed_ytd_gap':a(vals),
        'outside_effective_gap':a(inactive),
        'during_effective_gap':a(active),
        'active_days':len(active),
        'inactive_days':len(inactive),
        'current_active':bmeta['current_active'],
        'current_active_since':bmeta['current_active_since'],
        'current_cap':bmeta['current_cap'],
        'latest_total_stations':bmeta['latest_total_stations'],
        'latest_near_share':bmeta['latest_near_share'],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default='data-candidate.json')
    ap.add_argument('--output',default=None)
    args=ap.parse_args()
    path=Path(args.input); outpath=Path(args.output or args.input)
    data=json.loads(path.read_text(encoding='utf-8'))

    last_off=max(p[0] for p in data['G']['corse']['d'])
    last_date=ORIGIN+timedelta(days=last_off)
    bmeta=bd.metadata(last_date.year)
    meta={
        'last_date':str(last_date),
        'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'update_policy':'append-only',
        'bouclier':bmeta,
        'editorial':{
            'Gazole':editorial_for(data,'G','Gazole',bmeta['Gazole'],last_date.year),
            'SP95':editorial_for(data,'S','SP95',bmeta['SP95'],last_date.year),
        },
    }
    data['meta']=meta
    outpath.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    print('Wrote',outpath)

if __name__=='__main__': main()
