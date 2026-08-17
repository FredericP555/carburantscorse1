#!/usr/bin/env python3
import json
from datetime import date, timedelta
from pathlib import Path
import update_data_v2 as u

old = json.loads(Path('data.json').read_text(encoding='utf-8'))
new = json.loads(Path('data-new.json').read_text(encoding='utf-8'))
cut = (date(date.today().year,1,1)-u.ORIGIN).days

print('Lag test: old[d] compared with regenerated[d+lag]')
for fuel in ('G','S'):
    print(f'\n=== {fuel} ===')
    for region in ['corse','moy_regions'] + u.REGIONS:
        om = {p[0]:p[1] for p in old[fuel][region]['d'] if p[0] >= cut}
        nm = {p[0]:p[1] for p in new[fuel][region]['d'] if p[0] >= cut}
        scores = []
        for lag in (-2,-1,0,1,2):
            diffs=[]
            for k,ov in om.items():
                nv=nm.get(k+lag)
                if ov is not None and nv is not None:
                    diffs.append(abs(nv-ov))
            scores.append((sum(diffs)/len(diffs) if diffs else 999, lag))
        best=min(scores)
        s=' '.join(f'{lag:+d}:{mae*100:.2f}c' for mae,lag in scores)
        print(f'{region:28} {s}  BEST={best[1]:+d}')
