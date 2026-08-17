#!/usr/bin/env python3
"""Safety checks and concise report for an append-only candidate data file."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ORIGIN = date(2022,1,1)
REGIONS = [
    "corse","moy_regions","Auvergne-Rhône-Alpes","Bourgogne-Franche-Comté","Bretagne",
    "Centre-Val de Loire","Grand Est","Hauts-de-France","Île-de-France","Normandie",
    "Nouvelle-Aquitaine","Occitanie","PACA","Pays de la Loire",
]

old=json.loads(Path('data.json').read_text(encoding='utf-8'))
cand=json.loads(Path('data-candidate.json').read_text(encoding='utf-8'))

old_cut=max(p[0] for p in old['G']['corse']['d'])
ends=set()
for fuel in ('G','S'):
    for name in REGIONS:
        od=old[fuel][name]['d']
        cd=cand[fuel][name]['d']
        assert cd[:len(od)] == od, f'historical daily mutation: {fuel}/{name}'
        new=cd[len(od):]
        assert new, f'no appended points: {fuel}/{name}'
        expected=list(range(old_cut+1,new[-1][0]+1))
        actual=[p[0] for p in new]
        assert actual == expected, f'new daily segment not contiguous: {fuel}/{name}'
        ends.add(new[-1][0])
        for mode in ('w','m'):
            keys=[p[0] for p in cand[fuel][name][mode]]
            assert keys == sorted(keys), f'{mode} keys unsorted: {fuel}/{name}'
            assert len(keys)==len(set(keys)), f'{mode} duplicate keys: {fuel}/{name}'

assert len(ends)==1, f'series end on different offsets: {ends}'
end=next(iter(ends))
print('SAFETY CHECKS: OK')
print('Published daily history unchanged through', ORIGIN+timedelta(days=old_cut))
print('Candidate extends through', ORIGIN+timedelta(days=end))
print('New calendar days:', end-old_cut)

for fuel in ('G','S'):
    print(f'\n{fuel}:')
    for name in ('corse','moy_regions'):
        d=cand[fuel][name]['d'][-1]
        w=cand[fuel][name]['w'][-1]
        m=cand[fuel][name]['m'][-1]
        print(f'  {name:12} daily={d} weekly={w} monthly={m}')

print('\nFile sizes:')
print('  old      ', Path('data.json').stat().st_size)
print('  candidate', Path('data-candidate.json').stat().st_size)
