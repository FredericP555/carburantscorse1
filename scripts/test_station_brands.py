#!/usr/bin/env python3
from datetime import date

from ensure_station_brand_registry_policy import ensure_policy_metadata
from resolve_corse_station_brands_incremental import ids_to_fetch, ids_to_resolve
from update_corse_station_brands import (
    classify_brand,
    classify_station,
    extract_brand_from_html,
)

samples = {
    '<div><span>Marque :</span><strong>VITO</strong></div>': 'VITO',
    '<div>Marque : ENI</div>': 'ENI',
    '<dt>Marque :</dt><dd>TotalEnergies</dd>': 'TotalEnergies',
    '<dt>Marque :</dt><dd>TotalEnergies Access</dd>': 'TotalEnergies Access',
}
for raw, expected in samples.items():
    got = extract_brand_from_html(raw)
    assert got == expected, (raw, got, expected)

assert classify_brand('E.Leclerc') == ('gms_lowcost', 'gms')
assert classify_brand('TotalEnergies Access') == ('gms_lowcost', 'lowcost_major')
assert classify_brand('Esso Express') == ('gms_lowcost', 'lowcost_major')
assert classify_brand('TotalEnergies') == ('traditionnel', 'major_tradi')
assert classify_brand('ELAN') == ('traditionnel', 'major_tradi')
assert classify_brand('ENI') == ('traditionnel', 'major_tradi')
assert classify_brand('VITO') == ('traditionnel', 'marque_tradi')
assert classify_brand('MARIOTTI ENERG') == ('traditionnel', 'marque_tradi')
assert classify_brand(None) == ('inconnu', 'inconnu')
assert classify_brand('') == ('inconnu', 'inconnu')

by_brand = {
    'vito': {
        'segment': 'traditionnel',
        'detail': 'marque_tradi',
        'justification': 'test',
    }
}
by_id = {
    '20200001': {
        'segment': 'inconnu',
        'detail': 'inconnu',
        'justification': 'test override',
    }
}
assert classify_station('20200002', 'VITO', {}, by_brand) == (
    'traditionnel', 'marque_tradi', 'correction_marque'
)
assert classify_station('20200001', 'VITO', by_id, by_brand) == (
    'inconnu', 'inconnu', 'correction_id'
)

stations = {
    '20000006': {
        'enseigne': 'TotalEnergies', 'segment': 'traditionnel', 'active': True,
        'verified_at': '2026-09-01T00:00:00+00:00',
    },
    '20000007': {'enseigne': '', 'segment': 'inconnu', 'active': True},
    '20000008': {
        'enseigne': 'VITO', 'segment': 'traditionnel', 'active': True,
        'verified_at': '2026-01-01T00:00:00+00:00',
    },
}
assert ids_to_resolve({'20000006'}, stations) == []
assert ids_to_resolve({'20000006', '20000007', '20999999'}, stations) == [
    '20000007', '20999999'
]
assert ids_to_fetch(
    {'20000006', '20000008'}, stations,
    today=date(2026, 9, 8), reverify_days=90, limit=12,
) == ['20000008']

# Policy metadata must be persistable even when no station identity changed.
legacy_registry = {
    'schema': 'a4c-corsica-station-brands-v2',
    'classification': {
        'segments': ['gms_lowcost', 'traditionnel', 'inconnu'],
        'unknown_policy': 'inconnu is excluded from network comparisons',
        'corrections_file': 'config/corse_station_brand_corrections.csv',
    },
    'stations': {},
}
normalized, changed = ensure_policy_metadata(legacy_registry)
assert changed is True
assert normalized['classification']['brand_reverify_days'] == 90
assert normalized['classification']['brand_reverify_limit_per_run'] == 12
normalized_again, changed_again = ensure_policy_metadata(normalized)
assert changed_again is False
assert normalized_again == normalized

print('Station brand parser, A4C classification and temporal incremental resolution: OK')
