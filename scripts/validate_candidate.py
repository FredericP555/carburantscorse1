#!/usr/bin/env python3
"""Safety checks and concise report for an append-only candidate data file.

The validator is deliberately conservative: if a weekly update looks structurally impossible
or shows an implausibly large regional daily jump, publication stops instead of silently
feeding a suspicious value to the public dashboard.
"""
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
MAX_DAILY_MEAN_JUMP = 0.25  # €/L; fail-safe, not a smoothing rule
MIN_MEAN_PRICE = 0.80
MAX_MEAN_PRICE = 3.50
HT_TOLERANCE = 0.0025

old=json.loads(Path('data.json').read_text(encoding='utf-8'))
cand=json.loads(Path('data-candidate.json').read_text(encoding='utf-8'))

old_cut=max(p[0] for p in old['G']['corse']['d'])
ends=set()
new_lengths=[]

for fuel in ('G','S'):
    for name in REGIONS:
        od=old[fuel][name]['d']
        cd=cand[fuel][name]['d']
        assert cd[:len(od)] == od, f'historical daily mutation: {fuel}/{name}'
        new=cd[len(od):]
        new_lengths.append(len(new))

        if new:
            expected=list(range(old_cut+1,new[-1][0]+1))
            actual=[p[0] for p in new]
            assert actual == expected, f'new daily segment not contiguous: {fuel}/{name}'
            ends.add(new[-1][0])

            # Semantic fail-safes on the new segment. They do not alter prices; they only block
            # publication if the aggregate looks impossible and needs human inspection.
            previous=od[-1]
            vat=1.13 if name=='corse' else 1.20
            for point in new:
                off,ttc,ht=point
                assert ttc is not None and ht is not None, f'missing new daily price: {fuel}/{name}/{off}'
                assert MIN_MEAN_PRICE <= ttc <= MAX_MEAN_PRICE, f'implausible TTC mean: {fuel}/{name}/{off}={ttc}'
                expected_ht=ttc/vat
                assert abs(ht-expected_ht) <= HT_TOLERANCE, f'HT/TTC inconsistency: {fuel}/{name}/{off}: {ttc}/{ht}'
                if previous[1] is not None:
                    jump=abs(ttc-previous[1])
                    assert jump <= MAX_DAILY_MEAN_JUMP, f'implausible daily regional jump: {fuel}/{name}/{off} Δ={jump:.3f} €/L'
                previous=point

        for mode in ('w','m'):
            keys=[p[0] for p in cand[fuel][name][mode]]
            assert keys == sorted(keys), f'{mode} keys unsorted: {fuel}/{name}'
            assert len(keys)==len(set(keys)), f'{mode} duplicate keys: {fuel}/{name}'

# Either every series advanced together, or the run is a complete no-op.
if any(new_lengths):
    assert all(n>0 for n in new_lengths), f'only some series advanced: {new_lengths}'
    assert len(set(new_lengths))==1, f'series appended different day counts: {sorted(set(new_lengths))}'
    assert len(ends)==1, f'series end on different offsets: {ends}'
    end=next(iter(ends))
    new_days=end-old_cut
else:
    end=old_cut
    new_days=0

print('SAFETY CHECKS: OK')
print('Published daily history unchanged through', ORIGIN+timedelta(days=old_cut))
if new_days:
    print('Candidate extends through', ORIGIN+timedelta(days=end))
    print('New calendar days:', new_days)
else:
    print('No new official day — candidate is a clean no-op')

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
