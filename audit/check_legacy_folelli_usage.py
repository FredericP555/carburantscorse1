#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {'.git', 'audit', '__pycache__'}
EXCLUDE_FILES = {
    ROOT / 'config' / 'total_corse_stations.json',
    ROOT / 'config' / 'corse_station_brands.json',
}
NEEDLES = {
    'historical_aliases': 'historical_aliases',
    'legacy_registry_filename': 'total_corse_stations.json',
    'folelli_ids': None,
}
IDS = ('20213003', '20213007', '20213008')

hits: dict[str, list[str]] = {key: [] for key in NEEDLES}
for path in ROOT.rglob('*'):
    if not path.is_file():
        continue
    if any(part in EXCLUDE_DIRS for part in path.parts):
        continue
    if path in EXCLUDE_FILES:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    rel = str(path.relative_to(ROOT))
    if 'historical_aliases' in text:
        hits['historical_aliases'].append(rel)
    if 'total_corse_stations.json' in text:
        hits['legacy_registry_filename'].append(rel)
    if any(station_id in text for station_id in IDS):
        hits['folelli_ids'].append(rel)

for key, values in hits.items():
    print(f'H1_{key.upper()}_REF_COUNT={len(values)}')
    for value in values:
        print(f'  {value}')

assert not hits['historical_aliases'], hits
assert not hits['legacy_registry_filename'], hits
assert not hits['folelli_ids'], hits
print('H1_LEGACY_FOLELLI_USAGE=INERT')
