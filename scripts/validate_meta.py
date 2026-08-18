#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

data=json.loads(Path('data-candidate.json').read_text(encoding='utf-8'))
meta=data.get('meta') or {}
assert meta.get('last_date'), 'missing meta.last_date'
assert meta.get('update_policy')=='append-only'
assert meta.get('editorial_action_rule')=='union-of-gazole-and-sp95-total-intervention-periods'

editorial_ranges=None
for fuel in ('Gazole','SP95'):
    b=meta['bouclier'][fuel]
    e=meta['editorial'][fuel]
    assert isinstance(b['ranges'],list) and b['ranges']
    assert e['through']==meta['last_date']
    assert e['observed_ytd_gap'] is not None
    assert e['outside_total_action_gap'] is not None
    assert e['during_total_action_gap'] is not None
    assert e['total_action_days'] > 0
    assert e['outside_total_action_days'] > 0
    assert isinstance(e['total_action_ranges_used'],list) and e['total_action_ranges_used']

    # "Hors toute action TotalEnergies" uses one common calendar for both fuel analyses:
    # the union of Gazole + SP95 intervention periods.
    if editorial_ranges is None:
        editorial_ranges=e['total_action_ranges_used']
    else:
        assert e['total_action_ranges_used']==editorial_ranges, 'fuel-specific editorial action calendars diverged'

    # Registry/data coverage guardrails. The recovered registry has 47 current TotalEnergies
    # stations, but fuel availability differs: not every Total station necessarily has a fresh
    # SP95 state within the 45-day dashboard window.
    nt=b.get('latest_total_stations')
    nn=b.get('latest_non_total_stations')
    min_total={'Gazole':35,'SP95':25}[fuel]
    assert nt is not None and min_total <= nt <= 60, f'suspicious Total station coverage: {fuel}={nt}'
    assert nn is not None and nn >= 50, f'suspicious non-Total market coverage: {fuel}={nn}'
    assert b.get('latest_non_total_p75') is not None, f'missing non-Total p75: {fuel}'
    assert 0 <= b.get('latest_near_share',0) <= 1

    if b['current_active']:
        assert b['current_active_since']
        assert b['current_cap'] is not None
        assert b.get('latest_market_pressure') is True
        assert b['latest_near_share'] >= b['rule']['min_total_near_share']
        assert b['latest_non_total_p75'] >= b['current_cap']

    prev=None
    for r in b['ranges']:
        a=date.fromisoformat(r['d1']); z=date.fromisoformat(r['d2'])
        assert a<=z
        if prev is not None: assert a>prev
        prev=z

print('META SAFETY CHECKS: OK')
print(json.dumps(meta,ensure_ascii=False,indent=2))
