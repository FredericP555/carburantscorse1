#!/usr/bin/env python3
"""Calibrate a stable binary bouclier detector with two anti-flicker rules.

Raw signal: share of TotalEnergies Corsica stations close to the known ceiling.
Stability rules tested:
- fill short inactive gaps bounded by active days (promo/noise tolerance),
- remove isolated active runs that are too short.
The historical yellow zones remain the reference classification.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import calibrate_bouclier as base


def stable_flags(items, max_gap, min_run):
    # items sorted (date, raw_bool), possibly spanning several years.
    vals=[[d,b] for d,b in items]
    # Fill short FALSE runs only when bounded by TRUE on both sides and dates are contiguous.
    i=0
    while i < len(vals):
        if vals[i][1]:
            i+=1; continue
        j=i
        while j < len(vals) and not vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)):
            j+=1
        gap=j-i
        left = i>0 and vals[i-1][1] and vals[i][0]==vals[i-1][0]+timedelta(days=1)
        right = j<len(vals) and vals[j][1] and vals[j][0]==vals[j-1][0]+timedelta(days=1)
        if left and right and gap <= max_gap:
            for k in range(i,j): vals[k][1]=True
        i=j

    # Remove short TRUE runs.
    i=0
    while i < len(vals):
        if not vals[i][1]:
            i+=1; continue
        j=i
        while j < len(vals) and vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)):
            j+=1
        run=j-i
        if run < min_run:
            for k in range(i,j): vals[k][1]=False
        i=j
    return vals


def evaluate(rows,tol,thr,max_gap,min_run):
    grouped=defaultdict(list)
    actual={}
    for d,fuel,cap,prices in rows:
        if d > base.TRAIN_END: continue
        share=sum(1 for p in prices if cap-tol <= p <= cap+0.0015)/len(prices)
        grouped[fuel].append((d,share>=thr))
        actual[(fuel,d)]=base.manual_active(fuel,d)
    preds={}
    for fuel,items in grouped.items():
        items.sort()
        for d,b in stable_flags(items,max_gap,min_run): preds[(fuel,d)]=b
    tp=fp=tn=fn=0
    for key,a in actual.items():
        p=preds[key]
        if p and a: tp+=1
        elif p and not a: fp+=1
        elif not p and a: fn+=1
        else: tn+=1
    prec=tp/(tp+fp) if tp+fp else 0
    rec=tp/(tp+fn) if tp+fn else 0
    f1=2*prec*rec/(prec+rec) if prec+rec else 0
    spec=tn/(tn+fp) if tn+fp else 0
    bal=(rec+spec)/2
    return f1,bal,prec,rec,tp,fp,fn,tn


def ranges(items):
    out=[]; start=None; prev=None
    for d,b in items:
        if b and start is None: start=d
        if start is not None and (not b or (prev is not None and d != prev+timedelta(days=1))):
            out.append((start,prev)); start=d if b else None
        prev=d
    if start is not None: out.append((start,prev))
    return out


def main():
    rows=[]
    for y in (2023,2024,2025,2026): rows.extend(base.station_daily(y))

    results=[]
    for tol in (0.010,0.0125,0.015,0.020):
        for thr in (0.20,0.25,0.30,0.35,0.40):
            for gap in (0,2,3,4,5):
                for minrun in (1,3,5,7):
                    m=evaluate(rows,tol,thr,gap,minrun)
                    results.append((m[0],m[1],tol,thr,gap,minrun,*m[2:]))
    results.sort(reverse=True)
    print('Best stable rules by F1:')
    for r in results[:15]:
        f1,bal,tol,thr,gap,minrun,prec,rec,tp,fp,fn,tn=r
        print(f' tol={tol*100:.2f}c share>={thr:.0%} fill_gap<={gap}d min_run={minrun}d F1={f1:.3f} bal={bal:.3f} precision={prec:.3f} recall={rec:.3f} FP={fp} FN={fn}')

    f1,bal,tol,thr,gap,minrun,*_=results[0]
    print(f'\nSELECTED: tol={tol*100:.2f}c share>={thr:.0%}, fill gaps <= {gap}d, discard runs < {minrun}d')

    for fuel in ('Gazole','SP95'):
        raw=[]; stats=[]
        for d,f,cap,prices in rows:
            if f!=fuel or d.year!=2026: continue
            share=sum(1 for p in prices if cap-tol <= p <= cap+0.0015)/len(prices)
            raw.append((d,share>=thr)); stats.append((d,cap,len(prices),share))
        stable=stable_flags(raw,gap,minrun)
        print(f'\n{fuel} stable 2026 ranges:')
        for a,b in ranges(stable): print(' ',a,'->',b)
        print(f'{fuel} latest status:', stable[-1][0], 'ACTIVE' if stable[-1][1] else 'inactive', f'near-cap={stats[-1][3]:.1%}', f'n={stats[-1][2]}')

if __name__=='__main__': main()
