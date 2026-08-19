#!/usr/bin/env python3
from update_corse_station_brands import extract_brand_from_html, canonical_brand

samples = {
    '<div><span>Marque :</span><strong>VITO</strong></div>': 'VITO',
    '<div>Marque : ENI</div>': 'ENI',
    '<dt>Marque :</dt><dd>TotalEnergies</dd>': 'TotalEnergies',
    '<dt>Marque :</dt><dd>TotalEnergies Access</dd>': 'TotalEnergies Access',
}
for raw, expected in samples.items():
    got = extract_brand_from_html(raw)
    assert got == expected, (raw, got, expected)

assert canonical_brand('TotalEnergies Access') == 'TotalEnergies'
assert canonical_brand('TotalEnergies Contact') == 'TotalEnergies'
assert canonical_brand('VITO') == 'VITO'
assert canonical_brand('ENI') == 'ENI'
assert canonical_brand('MARIOTTI ENERG') == 'MARIOTTI ENERG'
print('Station brand parser: OK')
