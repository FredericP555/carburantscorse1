#!/usr/bin/env python3
"""Test whether legacy regional averages were equal-weight means of department averages."""
from collections import defaultdict
from datetime import date
import statistics
import update_data_v2 as u

CASES=[
    ('Centre-Val de Loire',date(2026,1,1),1.591),
    ('Centre-Val de Loire',date(2026,2,20),1.674),
    ('Centre-Val de Loire',date(2026,5,28),None),
    ('Bretagne',date(2026,4,7),2.281),
    ('Île-de-France',date(2026,3,3),1.840),
]

def combined():
    out=defaultdict(list)
    for y in (2025,2026):
        for k,v in u.parse_year(y).items(): out[k].extend(v)
    for v in out.values(): v.sort(key=lambda x:x[0])
    return out

def values(changes,region,d):
    rows=[]
    for (sid,reg,fuel),ups in changes.items():
        if reg!=region or fuel!='Gazole': continue
        last=None
        for ts,val in ups:
            if ts.date()<=d: last=(ts,val)
            else: break
        if last is None or (d-last[0].date()).days>u.MAX_FFILL_DAYS: continue
        # pdv id begins with the 5-digit postal code, so first 2 digits identify mainland department
        dep=sid[:2]
        rows.append((dep,sid,last[1]))
    return rows

def main():
    ch=combined()
    for region,d,target in CASES:
        rows=values(ch,region,d)
        station_mean=statistics.fmean(r[2] for r in rows)
        by=defaultdict(list)
        for dep,sid,val in rows: by[dep].append(val)
        dep_means={dep:statistics.fmean(vals) for dep,vals in by.items()}
        equal_dep=statistics.fmean(dep_means.values())
        print(f'\n{region} {d} n={len(rows)} deps={len(by)} target={target}')
        print(f' station-weighted={station_mean:.4f}  equal-department={equal_dep:.4f}')
        for dep in sorted(by): print(f'  {dep}: n={len(by[dep]):3d} mean={dep_means[dep]:.4f}')

if __name__=='__main__': main()
