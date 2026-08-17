#!/usr/bin/env python3
"""Compare regenerated data only near the published cutoff.

For append-only automation the historical data is immutable. What matters is that the
new method joins the last published days without creating an artificial step.
"""
from datetime import date, timedelta
import json
from pathlib import Path
import update_data_v2 as u

old=json.loads(Path('data.json').read_text(encoding='utf-8'))
new=u.payload(u.build_daily(date.today().year))
last_old=max(p[0] for p in old['G']['corse']['d'])
window_start=last_old-29
print('last published offset:', last_old, 'date:', u.ORIGIN+timedelta(days=last_old))
print('comparison window:', u.ORIGIN+timedelta(days=window_start), '->', u.ORIGIN+timedelta(days=last_old))

for fuel in ('G','S'):
    print(f'\n=== {fuel} last 30 published days ===')
    for region in ['corse','moy_regions']+u.REGIONS:
        om={p[0]:p[1] for p in old[fuel][region]['d'] if window_start <= p[0] <= last_old}
        nm={p[0]:p[1] for p in new[fuel][region]['d'] if p[0] in om}
        ds=[(k,nm[k]-ov) for k,ov in om.items() if k in nm and ov is not None and nm[k] is not None]
        if not ds:
            print(region, 'NO OVERLAP'); continue
        mae=sum(abs(x[1]) for x in ds)/len(ds)
        mx=max(ds,key=lambda x:abs(x[1]))
        boundary=nm.get(last_old)-om[last_old] if last_old in nm and last_old in om else None
        print(f'{region:28} MAE={mae*100:5.2f}c max={abs(mx[1])*100:5.2f}c boundary={boundary*100:+5.2f}c')

print('\nBoundary values (last published day):')
for fuel in ('G','S'):
    for region in ('corse','moy_regions'):
        om={p[0]:p[1] for p in old[fuel][region]['d']}
        nm={p[0]:p[1] for p in new[fuel][region]['d']}
        print(f'{fuel} {region:12}: old={om[last_old]:.3f} new={nm[last_old]:.3f} next={nm.get(last_old+1)}')
