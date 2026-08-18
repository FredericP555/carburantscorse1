#!/usr/bin/env python3
"""Regression checks for the shared c1 -> c2 annual snapshot window."""
from datetime import date

from export_shared_c2_snapshot import default_years


# On the last day of 2026, the producer still publishes 2025 + 2026.
assert default_years(date(2026, 12, 31)) == [2025, 2026]

# From 1 January 2027 onward, the shared snapshot must switch to 2026 + 2027.
assert default_years(date(2027, 1, 1)) == [2026, 2027]
assert default_years(date(2027, 1, 4)) == [2026, 2027]

print("Shared snapshot year window: OK")
