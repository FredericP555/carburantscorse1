#!/usr/bin/env python3
"""Detect when the TotalEnergies commercial ceiling is effectively constraining prices.

One rule is authoritative for carburantscorse1 and carburantscorse2. c1 calculates it and
publishes the resulting ranges in metadata; c2 consumes those ranges and does not redetect them.

A day is a raw active day when:
1. the applicable TotalEnergies ceiling is known;
2. at least one active TotalEnergies station is effectively at the ceiling, defined as within
   0.2 c/L below to 0.1 c/L above it;
3. the 75th percentile of active non-Total Corsica stations is at or above the ceiling.

A period is confirmed after 2 consecutive raw active days, but starts on the first of those two
days. Once periods are confirmed, a single inactive day between two confirmed runs is filled.
A lone active day is therefore never enough by itself, and two lone days separated by one day
cannot create a false period.

The 2023-2025 ranges were recomputed once with this exact rule from the official historical
stocks and are frozen below for reproducibility and weekly performance. From 2026 onward the
same rule is recomputed dynamically from the official annual stock.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import update_data_v2 as core

CAP_BELOW_TOLERANCE_EUR = 0.002
CAP_ABOVE_TOLERANCE_EUR = 0.001
MIN_TOTAL_AT_CAP_COUNT = 1
MARKET_QUANTILE = 0.75
MARKET_PRESSURE_TOLERANCE_EUR = 0.0
CONFIRMATION_DAYS = 2
MAX_GAP_DAYS = 1
MAX_AGE_DAYS = core.MAX_FFILL_DAYS
DYNAMIC_START_YEAR = 2026
HISTORICAL_RULE_FROZEN_THROUGH = date(2025, 12, 31)

REGISTRY = json.loads(Path('config/total_corse_stations.json').read_text(encoding='utf-8'))
CURRENT_TOTAL_IDS = set(REGISTRY['stations'])
HISTORICAL_TOTAL_IDS = set(REGISTRY.get('historical_aliases', {}))
TOTAL_IDS = CURRENT_TOTAL_IDS | HISTORICAL_TOTAL_IDS

# Recomputed from the official historical stocks with this exact rule on 19 Aug 2026.
HISTORICAL_RULE_RANGES = {
    'Gazole': [
        (date(2023, 9, 12), date(2023, 11, 2)),
    ],
    'SP95': [
        (date(2023, 3, 8), date(2023, 3, 17)),
        (date(2023, 3, 30), date(2023, 4, 30)),
        (date(2023, 7, 26), date(2023, 10, 10)),
        (date(2024, 3, 20), date(2024, 5, 27)),
    ],
}


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


def cap_for(fuel: str, d: date) -> float | None:
    """Return the formal TotalEnergies ceiling applicable on a date."""
    if fuel == 'SP95':
        return 1.99 if d >= date(2023, 3, 1) else None
    if fuel == 'Gazole':
        if date(2023, 3, 1) <= d <= date(2026, 3, 19):
            return 1.99
        if date(2026, 3, 20) <= d <= date(2026, 4, 7):
            return 2.09
        if d >= date(2026, 4, 8):
            return 2.25
    return None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    x = sorted(values)
    if len(x) == 1:
        return x[0]
    pos = (len(x) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(x) - 1)
    frac = pos - lo
    return x[lo] * (1 - frac) + x[hi] * frac


def _stable_flags(items: list[tuple[date, bool]]) -> list[tuple[date, bool]]:
    """Confirm 2-day runs first, then fill at most one day between confirmed runs."""
    vals = [[d, b] for d, b in sorted(items)]

    # First enforce the two-consecutive-day confirmation. This preserves the first day of a
    # confirmed run, so confirmation on day 2 is retroactive to day 1.
    i = 0
    while i < len(vals):
        if not vals[i][1]:
            i += 1
            continue
        j = i
        while (
            j < len(vals)
            and vals[j][1]
            and (j == i or vals[j][0] == vals[j - 1][0] + timedelta(days=1))
        ):
            j += 1
        if j - i < CONFIRMATION_DAYS:
            for k in range(i, j):
                vals[k][1] = False
        i = j

    # Only after confirmation may one isolated inactive day be filled between two confirmed
    # portions. Two raw singletons can therefore never be joined into a false active period.
    i = 0
    while i < len(vals):
        if vals[i][1]:
            i += 1
            continue
        j = i
        while (
            j < len(vals)
            and not vals[j][1]
            and (j == i or vals[j][0] == vals[j - 1][0] + timedelta(days=1))
        ):
            j += 1
        gap = j - i
        left = i > 0 and vals[i - 1][1] and vals[i][0] == vals[i - 1][0] + timedelta(days=1)
        right = j < len(vals) and vals[j][1] and vals[j][0] == vals[j - 1][0] + timedelta(days=1)
        if left and right and gap <= MAX_GAP_DAYS:
            for k in range(i, j):
                vals[k][1] = True
        i = j

    return [(d, b) for d, b in vals]


def _ranges(flags: list[tuple[date, bool]]) -> list[tuple[date, date]]:
    out = []
    start = None
    prev = None
    for d, b in flags:
        if b and start is None:
            start = d
        if start is not None and (not b or (prev is not None and d != prev + timedelta(days=1))):
            out.append((start, prev))
            start = d if b else None
        prev = d
    if start is not None:
        out.append((start, prev))
    return out


def _merge_ranges(ranges: list[tuple[date, date]]) -> list[tuple[date, date]]:
    if not ranges:
        return []
    out = []
    for a, b in sorted(ranges):
        if not out or a > out[-1][1] + timedelta(days=1):
            out.append([a, b])
        else:
            out[-1][1] = max(out[-1][1], b)
    return [(a, b) for a, b in out]


def detect_year(year: int | None = None) -> dict:
    year = year or date.today().year
    combined = defaultdict(list)
    for y in (year - 1, year):
        for (sid, region, fuel), vals in core.parse_year(y).items():
            if region == 'corse' and fuel in ('Gazole', 'SP95'):
                combined[(sid, fuel)].extend(vals)
    for vals in combined.values():
        vals.sort(key=lambda x: x[0])

    start = date(year, 1, 1)
    end = min(date(year, 12, 31), date.today() - timedelta(days=1))
    result = {}

    for fuel in ('Gazole', 'SP95'):
        station_ids = {sid for sid, f in combined if f == fuel}
        ptr = {sid: 0 for sid in station_ids}
        state = {sid: None for sid in station_ids}
        raw = []
        stats = {}
        d = start
        while d <= end:
            total_prices = []
            non_total_prices = []
            for sid in station_ids:
                vals = combined.get((sid, fuel), [])
                j = ptr[sid]
                while j < len(vals) and vals[j][0].date() <= d:
                    state[sid] = vals[j]
                    j += 1
                ptr[sid] = j
                st = state[sid]
                if st is None:
                    continue
                ts, value = st
                if (d - ts.date()).days > MAX_AGE_DAYS or value is None:
                    continue
                if sid in TOTAL_IDS:
                    total_prices.append(value)
                else:
                    non_total_prices.append(value)

            cap = cap_for(fuel, d)
            if cap is not None and total_prices and non_total_prices:
                at_cap = sum(
                    1
                    for p in total_prices
                    if cap - CAP_BELOW_TOLERANCE_EUR <= p <= cap + CAP_ABOVE_TOLERANCE_EUR
                )
                at_cap_share = at_cap / len(total_prices)
                market_p75 = percentile(non_total_prices, MARKET_QUANTILE)
                pressure = (
                    market_p75 is not None
                    and market_p75 >= cap - MARKET_PRESSURE_TOLERANCE_EUR
                )
                raw_active = at_cap >= MIN_TOTAL_AT_CAP_COUNT and pressure
                raw.append((d, raw_active))
                stats[d] = {
                    'cap': cap,
                    'total_stations': len(total_prices),
                    'non_total_stations': len(non_total_prices),
                    'at_cap_count': at_cap,
                    'at_cap_share': at_cap_share,
                    # Backward-compatible aliases used by existing summaries.
                    'near_count': at_cap,
                    'near_share': at_cap_share,
                    'non_total_p75': market_p75,
                    'market_pressure': pressure,
                    'raw_active': raw_active,
                    'total_min_price': min(total_prices),
                    'total_max_price': max(total_prices),
                }
            d += timedelta(days=1)

        stable = _stable_flags(raw)
        result[fuel] = {
            'flags': dict(stable),
            'detected_ranges': _ranges(stable),
            'stats': stats,
        }
    return result


def display_ranges(fuel: str, detected_by_year: dict[int, dict], through_year: int) -> list[tuple[date, date]]:
    """Combine rule-derived frozen history with dynamic ranges from 2026 onward."""
    ranges = [
        (a, b)
        for a, b in HISTORICAL_RULE_RANGES[fuel]
        if a.year <= through_year
    ]
    for y in sorted(detected_by_year):
        ranges.extend(detected_by_year[y][fuel]['detected_ranges'])
    return _merge_ranges(ranges)


def metadata(year: int | None = None) -> dict:
    year = year or date.today().year

    if year >= DYNAMIC_START_YEAR:
        detected_by_year = {
            y: detect_year(y)
            for y in range(DYNAMIC_START_YEAR, year + 1)
        }
        current_det = detected_by_year[year]
    else:
        # Kept for diagnostic/backfill use. Production currently runs from 2026 onward.
        detected_by_year = {}
        current_det = detect_year(year)

    out = {}
    for fuel in ('Gazole', 'SP95'):
        ranges = display_ranges(fuel, detected_by_year, year)
        stats = current_det[fuel]['stats']
        latest = max(stats) if stats else None
        latest_flag = current_det[fuel]['flags'].get(latest, False) if latest else False
        active_since = None
        if latest_flag and latest is not None:
            for a, b in ranges:
                if a <= latest <= b:
                    active_since = a
                    break

        s = stats.get(latest, {}) if latest else {}
        at_cap_share = s.get('at_cap_share') if s else None
        out[fuel] = {
            'ranges': [{'d1': str(a), 'd2': str(b)} for a, b in ranges],
            'current_active': bool(latest_flag),
            'current_active_since': str(active_since) if active_since else None,
            'current_cap': s.get('cap'),
            'latest_total_stations': s.get('total_stations'),
            'latest_non_total_stations': s.get('non_total_stations'),
            'latest_at_cap_count': s.get('at_cap_count'),
            'latest_at_cap_share': round(at_cap_share, 4) if at_cap_share is not None else None,
            # Backward-compatible name retained for existing editorial consumers.
            'latest_near_share': round(at_cap_share, 4) if at_cap_share is not None else None,
            'latest_non_total_p75': round(s.get('non_total_p75'), 3) if s.get('non_total_p75') is not None else None,
            'latest_market_pressure': s.get('market_pressure'),
            'rule': {
                'definition': '>=1 station Total au plafond ET P75 hors Total >= plafond',
                'cap_tolerance_below_cents': CAP_BELOW_TOLERANCE_EUR * 100,
                'cap_tolerance_above_cents': CAP_ABOVE_TOLERANCE_EUR * 100,
                'min_total_at_cap_count': MIN_TOTAL_AT_CAP_COUNT,
                'market_reference': '75e percentile des stations corses non-Total',
                'market_pressure_threshold': '>= plafond',
                'confirmation_days': CONFIRMATION_DAYS,
                'confirmation_retroactive_to_first_day': True,
                'fill_gap_days': MAX_GAP_DAYS,
                'historical_ranges_recomputed_through': str(HISTORICAL_RULE_FROZEN_THROUGH),
            },
        }
    return out


if __name__ == '__main__':
    print(json.dumps(metadata(), ensure_ascii=False, indent=2))
