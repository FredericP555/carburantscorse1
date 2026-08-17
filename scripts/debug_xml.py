#!/usr/bin/env python3
import io
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

URLS = [
    (2025, 'https://donnees.roulez-eco.fr/opendata/annee/2025'),
    (2026, 'https://donnees.roulez-eco.fr/opendata/annee'),
]

for year, url in URLS:
    print(f'\n=== {year} ===')
    req = urllib.request.Request(url, headers={'User-Agent':'A4C-observatoire-debug/1.0'})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    print('download bytes:', len(data))
    zf = zipfile.ZipFile(io.BytesIO(data))
    print('zip members:', zf.namelist()[:5])
    xml_name = next(n for n in zf.namelist() if n.lower().endswith('.xml'))

    tags = Counter()
    pdv_count = 0
    pdv_with_prices = 0
    price_count = 0
    fuels = Counter()
    min_dt = None
    max_dt = None
    first_pdv = None
    first_prices = []

    with zf.open(xml_name) as fh:
        for event, elem in ET.iterparse(fh, events=('end',)):
            local = elem.tag.rsplit('}',1)[-1]
            tags[local] += 1
            if local != 'pdv':
                continue
            pdv_count += 1
            children = list(elem)
            prices = [p for p in children if p.tag.rsplit('}',1)[-1] == 'prix']
            if prices:
                pdv_with_prices += 1
            if first_pdv is None:
                first_pdv = dict(elem.attrib)
                first_prices = [dict(p.attrib) for p in prices[:6]]
            for p in prices:
                price_count += 1
                fuels[p.attrib.get('nom','?')] += 1
                raw = p.attrib.get('maj')
                if raw:
                    try:
                        dt = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
                        min_dt = dt if min_dt is None or dt < min_dt else min_dt
                        max_dt = dt if max_dt is None or dt > max_dt else max_dt
                    except ValueError:
                        pass
            elem.clear()

    print('top tags:', tags.most_common(10))
    print('pdv_count:', pdv_count)
    print('pdv_with_prices:', pdv_with_prices)
    print('price_count:', price_count)
    print('fuels:', fuels)
    print('min/max maj:', min_dt, max_dt)
    print('first pdv attrs:', first_pdv)
    print('first price attrs:', first_prices)
