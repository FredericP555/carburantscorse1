from pathlib import Path
p=Path('scripts/bouclier_detector.py')
s=p.read_text(encoding='utf-8')
if 'LEGACY_RANGES = {' not in s:
    anchor='\n\ndef cap_for(fuel: str, d: date) -> float | None:\n'
    block="""

# Historical editorial compatibility only. These recovered action windows reproduce the
# published "hors toute action TotalEnergies" analysis; they are NOT used to draw the
# effective-ceiling yellow zones, which come from HISTORICAL_RULE_RANGES + dynamic detection.
LEGACY_RANGES = {
    'Gazole': [
        (date(2023, 8, 31), date(2023, 10, 13)),
        (date(2023, 10, 24), date(2023, 10, 30)),
        (date(2026, 3, 20), date(2026, 4, 6)),
        (date(2026, 4, 8), date(2026, 5, 27)),
    ],
    'SP95': [
        (date(2023, 2, 20), date(2023, 3, 19)),
        (date(2023, 3, 27), date(2023, 5, 2)),
        (date(2023, 6, 9), date(2023, 6, 21)),
        (date(2023, 7, 25), date(2023, 10, 7)),
        (date(2024, 2, 20), date(2024, 3, 1)),
        (date(2024, 3, 7), date(2024, 6, 5)),
        (date(2024, 7, 1), date(2024, 7, 16)),
        (date(2026, 3, 13), date(2026, 5, 28)),
    ],
}
"""
    if anchor not in s:
        raise SystemExit('cap_for anchor not found')
    s=s.replace(anchor,block+anchor,1)
p.write_text(s,encoding='utf-8')
