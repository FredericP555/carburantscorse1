#!/usr/bin/env python3
"""Calibrate a simple, auditable 'bouclier effectif' detector.

The historical yellow zones already present in app.js are treated as the reference labels.
We test rules of the form:
    active = share of active TotalEnergies Corsica stations within X c/L below the cap >= Y
No model/AI is involved: the goal is a transparent threshold that best reproduces the manual
historical classification, then can be applied prospectively.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

REGISTRY = json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))['stations']
TOTAL_IDS = set(REGISTRY)
MAX_AGE = core.MAX_FFILL_DAYS

MANUAL = {
    'Gazole': [
        ('2023-08-31','2023-10-13'),('2023-10-24','2023-10-30'),
        ('2026-03-20','2026-04-06'),('2026-04-08','2026-05-27'),
    ],
    'SP95': [
        ('2023-02-20','2023-03-19'),('2023-03-27','2023-05-02'),
        ('2023-06-09','2023-06-21'),('2023-07-25','2023-10-07'),
        ('2024-02-20','2024-03-01'),('2024-03-07','2024-06-05'),
        ('2024-07-01','2024-07-16'),('2026-03-13','2026-05-28'),
    ],
}

TRAIN_END = date(2026,5,28)


def D(s): return date.fromisoformat(s)


def manual_active(fuel, d):
    return any(D(a) <= d <= D(b) for a,b in MANUAL[fuel])


def cap_for(fuel, d):
    # Commercial ceiling relevant for the historical/current distribution test.
    if fuel == 'SP95':
        if d >= date(2023,2,1):
            return 1.99
        return None
    if fuel == 'Gazole':
        if date(2023,2,1) <= d <= date(2025,12,31):
            return 1.99
        if date(2026,1,1) <= d <= date(2026,3,11):
            return 1.99
        if date(2026,3,12) <= d <= date(2026,4,7):
            return 2.09
        if d >= date(2026,4,8):
            return 2.25
    return None


def station_daily(year):
    parsed = core.parse_year(year)
    updates = {}
    for (sid, region, fuel), vals in parsed.items():
        if region == 'corse' and sid in TOTAL_IDS and fuel in ('Gazole','SP95'):
            vals.sort(key=lambda x:x[0])
            updates[(sid,fuel)] = vals
    start=date(year,1,1)
    end=min(date(year,12,31), date.today()-timedelta(days=1))
    out=[]
    for fuel in ('Gazole','SP95'):
        pointers={}
        state={}
        for sid in TOTAL_IDS:
            vals=updates.get((sid,fuel),[])
            pointers[sid]=0
            state[sid]=None
        d=start
        while d<=end:
            prices=[]
            for sid in TOTAL_IDS:
                vals=updates.get((sid,fuel),[])
                j=pointers[sid]
                while j < len(vals) and vals[j][0].date() <= d:
                    state[sid]=vals[j]
                    j += 1
                pointers[sid]=j
                st=state[sid]
                if st is not None and (d-st[0].date()).days <= MAX_AGE:
                    prices.append(st[1])
            cap=cap_for(fuel,d)
            if cap is not None and prices:
                out.append((d,fuel,cap,prices))
            d += timedelta(days=1)
    return out


def metrics(rows, tol, threshold):
    tp=fp=tn=fn=0
    for d,fuel,cap,prices in rows:
        if d > TRAIN_END: continue
        share=sum(1 for p in prices if cap-tol <= p <= cap+0.0015)/len(prices)
        pred=share >= threshold
        actual=manual_active(fuel,d)
        if pred and actual: tp+=1
        elif pred and not actual: fp+=1
        elif not pred and actual: fn+=1
        else: tn+=1
    precision=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0
    specificity=tn/(tn+fp) if tn+fp else 0
    bal=(recall+specificity)/2
    return f1,bal,precision,recall,tp,fp,fn,tn


def ranges_from_flags(items):
    # items: sorted (date, bool); only TRUE ranges returned.
    ranges=[]; start=None; prev=None
    for d,flag in items:
        if flag and start is None:
            start=d
        if start is not None and (not flag or (prev is not None and d != prev+timedelta(days=1))):
            ranges.append((start,prev))
            start=d if flag else None
        prev=d
    if start is not None: ranges.append((start,prev))
    return ranges


def main():
    rows=[]
    for y in (2023,2024,2025,2026):
        rows.extend(station_daily(y))
    print('Total station registry:',len(TOTAL_IDS))
    print('Daily fuel/cap rows:',len(rows))

    results=[]
    for tol in (0.003,0.005,0.0075,0.010,0.0125,0.015,0.020):
        for threshold in [x/100 for x in range(10,81,5)]:
            m=metrics(rows,tol,threshold)
            results.append((m[0],m[1],tol,threshold,*m[2:]))
    results.sort(reverse=True)
    print('\nBest simple rules by F1:')
    for r in results[:12]:
        f1,bal,tol,thr,prec,rec,tp,fp,fn,tn=r
        print(f' tol={tol*100:4.2f}c share>={thr:4.0%} F1={f1:.3f} bal={bal:.3f} precision={prec:.3f} recall={rec:.3f} TP={tp} FP={fp} FN={fn}')

    _,_,tol,thr,*_=results[0]
    print(f'\nSelected diagnostic rule: within {tol*100:.2f} c/L of cap, share >= {thr:.0%}')

    # Report current 2026 dates and resulting raw TRUE ranges.
    for fuel in ('Gazole','SP95'):
        flags=[]
        stats=[]
        for d,f,cap,prices in rows:
            if f!=fuel or d.year!=2026: continue
            share=sum(1 for p in prices if cap-tol <= p <= cap+0.0015)/len(prices)
            flags.append((d,share>=thr))
            stats.append((d,cap,len(prices),share,min(prices),max(prices)))
        print(f'\n{fuel} — raw detected 2026 ranges:')
        for a,b in ranges_from_flags(flags): print(' ',a,'->',b)
        print(f'{fuel} — last 21 available days:')
        for d,cap,n,share,pmin,pmax in stats[-21:]:
            print(f' {d} cap={cap:.2f} n={n:2d} near={share:5.1%} min={pmin:.3f} max={pmax:.3f}')

if __name__=='__main__': main()
