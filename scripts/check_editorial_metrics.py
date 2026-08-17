#!/usr/bin/env python3
"""Recover the formulas behind the currently hard-coded editorial figures.

Uses only the published data.json and the currently hard-coded intervention periods.
No upstream download, no mutation.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ORIGIN=date(2022,1,1)
REM_2022=[(date(2022,9,1),date(2022,12,31))]
BOUCLIER={
 'G':[('2023-08-31','2023-10-13'),('2023-10-24','2023-10-30'),('2026-03-20','2026-04-06'),('2026-04-08','2026-05-27')],
 'S':[('2023-02-20','2023-03-19'),('2023-03-27','2023-05-02'),('2023-06-09','2023-06-21'),('2023-07-25','2023-10-07'),('2024-02-20','2024-03-01'),('2024-03-07','2024-06-05'),('2024-07-01','2024-07-16'),('2026-03-13','2026-05-28')],
}
HARDCODED={
 'G': {'trend':{2022:15.3,2023:17.3,2024:18.1,2025:18.3},'with22':12.2,'without22':15.3,'with26':12.8,'without26':15.3,'min':-1.1},
 'S': {'trend':{2022:14.2,2023:14.3,2024:17.2,2025:17.3},'with22':10.6,'without22':14.2,'with26':12.4,'without26':16.4,'min':-6.8},
}

def D(s): return date.fromisoformat(s)

def inside(d,ranges):
    return any((D(a) if isinstance(a,str) else a) <= d <= (D(b) if isinstance(b,str) else b) for a,b in ranges)

def avg(xs): return sum(xs)/len(xs) if xs else None

def f1(x): return None if x is None else round(x,1)

def main():
    data=json.loads(Path('data.json').read_text(encoding='utf-8'))
    for fuel in ('G','S'):
        c={p[0]:p[2] for p in data[fuel]['corse']['d']}
        r={p[0]:p[2] for p in data[fuel]['moy_regions']['d']}
        rows=[]
        for off,hc in c.items():
            hr=r.get(off)
            if hc is None or hr is None: continue
            d=ORIGIN+timedelta(days=off)
            rows.append((d,(hc-hr)*100))
        print(f'\n===== {fuel} =====')
        for year in (2022,2023,2024,2025,2026):
            yr=[(d,v) for d,v in rows if d.year==year]
            allavg=avg([v for d,v in yr])
            if year==2022:
                clean=avg([v for d,v in yr if not inside(d,REM_2022)])
            else:
                clean=avg([v for d,v in yr if not inside(d,BOUCLIER[fuel])])
            excluded=len(yr)-len([1 for d,v in yr if (not inside(d,REM_2022) if year==2022 else not inside(d,BOUCLIER[fuel]))])
            print(f'{year}: all={allavg:.3f} -> {f1(allavg):.1f} | outside intervention={clean:.3f} -> {f1(clean):.1f} | n={len(yr)} excluded={excluded}')
        mn=min(rows,key=lambda x:x[1])
        print('global minimum:',mn[0],f'{mn[1]:.3f} -> {f1(mn[1]):.1f}')
        h=HARDCODED[fuel]
        print('hardcoded:',h)

if __name__=='__main__': main()
