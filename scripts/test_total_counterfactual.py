#!/usr/bin/env python3
"""Test whether legacy Gazole 'without Total intervention' figures came from excluding Total stations.

For Corsica, the TotalEnergies station registry is known. We rebuild daily Corsica averages
for all stations and for non-Total stations only, then compare both (HT) with the published
moy_regions daily HT series in data.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import statistics

import update_data_v2 as core

TOTAL_IDS=set(json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))['stations'])
ORIGIN=core.ORIGIN


def active_station_values(year:int, fuel:str):
    combined=defaultdict(list)
    for y in (year-1,year):
        for (sid,region,f),vals in core.parse_year(y).items():
            if region=='corse' and f==fuel:
                combined[sid].extend(vals)
    for vals in combined.values(): vals.sort(key=lambda x:x[0])
    start=date(year,1,1)
    end=min(date(year,12,31),date.today()-timedelta(days=1))
    states={sid:None for sid in combined}
    ptr={sid:0 for sid in combined}
    out={}
    d=start
    while d<=end:
        allp=[]; non_total=[]; total=[]
        for sid,vals in combined.items():
            j=ptr[sid]
            while j<len(vals) and vals[j][0].date()<=d:
                states[sid]=vals[j]; j+=1
            ptr[sid]=j
            st=states[sid]
            if st is None or (d-st[0].date()).days>core.MAX_FFILL_DAYS: continue
            p=st[1]
            allp.append(p)
            (total if sid in TOTAL_IDS else non_total).append(p)
        if allp:
            out[d]={
                'all':statistics.fmean(allp),
                'non_total':statistics.fmean(non_total) if non_total else None,
                'total':statistics.fmean(total) if total else None,
                'n_all':len(allp),'n_non':len(non_total),'n_total':len(total),
            }
        d+=timedelta(days=1)
    return out


def avg(xs): return statistics.fmean(xs) if xs else None


def main():
    published=json.loads(Path('data.json').read_text(encoding='utf-8'))
    for year in (2023,2026):
        vals=active_station_values(year,'Gazole')
        reg={ORIGIN+timedelta(days=p[0]):p[2] for p in published['G']['moy_regions']['d']}
        rows=[]
        for d,x in vals.items():
            if d not in reg: continue
            mainland_ht=reg[d]
            all_gap=(x['all']/1.13-mainland_ht)*100
            non_gap=(x['non_total']/1.13-mainland_ht)*100 if x['non_total'] is not None else None
            total_gap=(x['total']/1.13-mainland_ht)*100 if x['total'] is not None else None
            rows.append((d,all_gap,non_gap,total_gap,x))
        print(f'\n===== GAZOLE {year} =====')
        print('published overlap days:',len(rows))
        print('all Corse rebuilt gap:',avg([r[1] for r in rows]))
        print('NON-TOTAL Corse gap:',avg([r[2] for r in rows if r[2] is not None]))
        print('TOTAL-only Corse gap:',avg([r[3] for r in rows if r[3] is not None]))
        if rows:
            last=rows[-1]
            print('last date',last[0], 'n all/non/total',last[4]['n_all'],last[4]['n_non'],last[4]['n_total'])
            print('last gaps all/non/total',last[1],last[2],last[3])

if __name__=='__main__': main()
