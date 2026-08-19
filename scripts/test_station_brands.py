#!/usr/bin/env python3
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

# A4C segmentation: tariff behaviour, not ownership category.
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

# Brand correction applies first; station-ID correction has final priority.
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

print('Station brand parser and A4C classification: OK')
