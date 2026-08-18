#!/usr/bin/env python3
"""Regression checks for the weekly updater around 31 December / 1 January."""
from datetime import date

from update_data_append import ORIGIN, generation_years


def off(d: date) -> int:
    return (d - ORIGIN).days


# Exact failure mode reported during review: history stops on 27 Dec, next run is in 2027.
assert generation_years(off(date(2026, 12, 27)), 2027) == [2026, 2027]

# Once the previous year is complete, only the current year is needed.
assert generation_years(off(date(2026, 12, 31)), 2027) == [2027]

# Ordinary in-year weekly run remains unchanged.
assert generation_years(off(date(2026, 8, 17)), 2026) == [2026]

print("Year-boundary generation window: OK")
