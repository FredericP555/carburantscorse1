#!/usr/bin/env python3
import json
from datetime import date, timedelta
from pathlib import Path
import update_data_v2 as u

old = json.loads(Path('data.json').read_text(encoding='utf-8'))
new = u.payload(u.build_daily(date.today().year))
cut = (date(date.today().year,1,1)-u.ORIGIN).days

for fuel in ('G','S'):
    print(f'\n===== {fuel} =====')
    for region in ['corse','moy_regions'] + u.REGIONS:
        om = {p[0]:p[1] for p in old[fuel][region]['d'] if p[0] >= cut}
        nm = {p[0]:p[1] for p in new[fuel][region]['d'] if p[0] in om}
        diffs = []
        for k, nv in nm.items():
            ov = om.get(k)
            if nv is None or ov is None:
                continue
            diffs.append((abs(nv-ov), k, ov, nv, nv-ov))
        diffs.sort(reverse=True)
        worst = diffs[:5]
        if worst and worst[0][0] >= 0.008:
            print(f'\n{region}')
            for ad, off, ov, nv, signed in worst:
                d = u.ORIGIN + timedelta(days=off)
                print(f'  {d}: old={ov:.3f} new={nv:.3f} delta={signed:+.3f}')
