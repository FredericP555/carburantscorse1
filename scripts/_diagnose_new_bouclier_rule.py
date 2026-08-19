from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

BELOW=0.002
ABOVE=0.001
Q=0.75
MAX_GAP=1
MIN_RUN=2
MAX_AGE=core.MAX_FFILL_DAYS
REGISTRY=json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))
TOTAL_IDS=set(REGISTRY['stations'])|set(REGISTRY.get('historical_aliases',{}))


def cap_for(fuel,d):
    if fuel=='SP95':
        return 1.99 if d>=date(2023,3,1) else None
    if fuel=='Gazole':
        if date(2023,3,1)<=d<=date(2026,3,19): return 1.99
        if date(2026,3,20)<=d<=date(2026,4,7): return 2.09
        if d>=date(2026,4,8): return 2.25
    return None


def percentile(values,q):
    if not values:return None
    x=sorted(values)
    if len(x)==1:return x[0]
    pos=(len(x)-1)*q; lo=int(pos); hi=min(lo+1,len(x)-1); f=pos-lo
    return x[lo]*(1-f)+x[hi]*f


def stable(items):
    vals=[[d,b] for d,b in sorted(items)]
    i=0
    while i<len(vals):
        if vals[i][1]: i+=1; continue
        j=i
        while j<len(vals) and not vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)): j+=1
        gap=j-i
        left=i>0 and vals[i-1][1] and vals[i][0]==vals[i-1][0]+timedelta(days=1)
        right=j<len(vals) and vals[j][1] and vals[j][0]==vals[j-1][0]+timedelta(days=1)
        if left and right and gap<=MAX_GAP:
            for k in range(i,j): vals[k][1]=True
        i=j
    i=0
    while i<len(vals):
        if not vals[i][1]: i+=1; continue
        j=i
        while j<len(vals) and vals[j][1] and (j==i or vals[j][0]==vals[j-1][0]+timedelta(days=1)): j+=1
        if j-i<MIN_RUN:
            for k in range(i,j): vals[k][1]=False
        i=j
    return vals


def ranges(vals):
    out=[]; start=None; prev=None
    for d,b in vals:
        if b and start is None:start=d
        if start is not None and (not b or (prev is not None and d!=prev+timedelta(days=1))):
            out.append((start,prev)); start=d if b else None
        prev=d
    if start is not None: out.append((start,prev))
    return out


def detect_year(year):
    combined=defaultdict(list)
    for y in (year-1,year):
        for (sid,region,fuel),vals in core.parse_year(y).items():
            if region=='corse' and fuel in ('Gazole','SP95'): combined[(sid,fuel)].extend(vals)
    for vals in combined.values(): vals.sort(key=lambda x:x[0])
    end=min(date(year,12,31),date.today()-timedelta(days=1))
    result={}
    for fuel in ('Gazole','SP95'):
        station_ids={sid for sid,f in combined if f==fuel}; ptr={sid:0 for sid in station_ids}; state={sid:None for sid in station_ids}; raw=[]
        d=date(year,1,1)
        while d<=end:
            t=[]; n=[]
            for sid in station_ids:
                vals=combined.get((sid,fuel),[]); j=ptr[sid]
                while j<len(vals) and vals[j][0].date()<=d:
                    state[sid]=vals[j]; j+=1
                ptr[sid]=j; st=state[sid]
                if st is None: continue
                ts,val=st
                if (d-ts.date()).days>MAX_AGE or val is None: continue
                (t if sid in TOTAL_IDS else n).append(val)
            cap=cap_for(fuel,d)
            if cap is not None and t and n:
                at_cap=sum(1 for p in t if cap-BELOW<=p<=cap+ABOVE)
                p75=percentile(n,Q)
                raw.append((d,at_cap>=1 and p75 is not None and p75>=cap))
            d+=timedelta(days=1)
        result[fuel]=ranges(stable(raw))
    return result


for y in (2023,2024,2025,2026):
    r=detect_year(y)
    print('YEAR',y)
    for fuel in ('Gazole','SP95'):
        print(fuel,[{'d1':str(a),'d2':str(b)} for a,b in r[fuel]])
