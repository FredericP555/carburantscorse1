#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

data=json.loads(Path('data-candidate.json').read_text(encoding='utf-8'))
meta=data.get('meta') or {}
assert meta.get('last_date'), 'missing meta.last_date'
assert meta.get('update_policy')=='append-only'
for fuel in ('Gazole','SP95'):
    b=meta['bouclier'][fuel]
    e=meta['editorial'][fuel]
    assert isinstance(b['ranges'],list) and b['ranges']
    assert e['through']==meta['last_date']
    assert e['observed_ytd_gap'] is not None
    assert e['outside_effective_gap'] is not None
    if b['current_active']:
        assert b['current_active_since']
        assert b['current_cap'] is not None
        assert 0 <= b['latest_near_share'] <= 1
    # ranges must be ordered and valid
    prev=None
    for r in b['ranges']:
        a=date.fromisoformat(r['d1']); z=date.fromisoformat(r['d2'])
        assert a<=z
        if prev is not None: assert a>prev
        prev=z
print('META SAFETY CHECKS: OK')
print(json.dumps(meta,ensure_ascii=False,indent=2))
