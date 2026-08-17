#!/usr/bin/env python3
"""Test counterfactual Gazole 2026: during effective-ceiling days, replace Total station
prices by the average non-Total Corsica price, keeping actual values otherwise.

This tests whether the legacy 'sans bouclier' 15.3 c/L was a modeled counterfactual rather
than a mean of observed non-yellow days.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import statistics

import update_data_v2 as core

ORIGIN=core.ORIGIN
TOTAL_IDS=set(json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))['stations'])
# Use the old displayed effective period, then also the newly calibrated near-equivalent period.
PERIOD_SETS={
    'legacy': [(date(2026,3,20),date(2026,4,6)),(date(2026,4,8),date(2026,5,27))],
    'stable_calibration': [(date(2026,3,20),date(2026,5,26))],
}

def inside(d,ranges): return any(a<=d<=b for a,b in ranges)

def station_states(year=2026):
    combined=defaultdict(list)
    for y in (year-1,year):
        for (sid,reg,fuel),vals in core.parse_year(y).items():
            if reg=='corse' and fuel=='Gazole': combined[sid].extend(vals)
    for vals in combined.values(): vals.sort(key=lambda x:x[0])
    states={sid:None for sid in combined}; ptr={sid:0 for sid in combined}
    start=date(year,1,1); end=date(2026,5,28)
    out={}; d=start
    while d<=end:
        total=[]; non=[]
        for sid,vals in combined.items():
            j=ptr[sid]
            while j<len(vals) and vals[j][0].date()<=d:
                states[sid]=vals[j]; j+=1
            ptr[sid]=j
            st=states[sid]
            if st is None or (d-st[0].date()).days>core.MAX_FFILL_DAYS: continue
            (total if sid in TOTAL_IDS else non).append(st[1])
        if total and non:
            out[d]=(total,non)
        d+=timedelta(days=1)
    return out

def avg(xs): return statistics.fmean(xs)

def main():
    data=json.loads(Path('data.json').read_text(encoding='utf-8'))
    mainland={ORIGIN+timedelta(days=p[0]):p[2] for p in data['G']['moy_regions']['d']}
    published_corse={ORIGIN+timedelta(days=p[0]):p[2] for p in data['G']['corse']['d']}
    states=station_states()

    actual=[(published_corse[d]-mainland[d])*100 for d in published_corse if d.year==2026 and d in mainland]
    print('published actual YTD gap:',avg(actual))

    for label,ranges in PERIOD_SETS.items():
        cf=[]; active_non=[]; active_total=[]; active_actual=[]
        for d,(tot,non) in states.items():
            if d not in mainland: continue
            n_t=len(tot); n_n=len(non); n=n_t+n_n
            all_ttc=(sum(tot)+sum(non))/n
            if inside(d,ranges):
                nonmean=avg(non)
                # Counterfactual: each Total station priced at the same average as non-Total stations.
                cf_ttc=(nonmean*n_t + sum(non))/n
                active_non.append((nonmean/1.13-mainland[d])*100)
                active_total.append((avg(tot)/1.13-mainland[d])*100)
                active_actual.append((all_ttc/1.13-mainland[d])*100)
            else:
                cf_ttc=all_ttc
            cf.append((cf_ttc/1.13-mainland[d])*100)
        print(f'\n{label}:')
        print(' counterfactual YTD:',avg(cf))
        print(' active days:',sum((b-a).days+1 for a,b in ranges))
        print(' active non-Total gap:',avg(active_non))
        print(' active Total-only gap:',avg(active_total))
        print(' active all gap:',avg(active_actual))
        print(' active network difference non-total minus Total:',avg(active_non)-avg(active_total))

if __name__=='__main__': main()
