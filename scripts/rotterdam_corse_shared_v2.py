#!/usr/bin/env python3
"""Canonical prepared Corsica Rotterdam calibration produced upstream by C1.

C1 owns the single UFIP download. R2 is an admissibility threshold for stale
station prices in the double-cap case; it never defines whether the shield
itself is effective.

Once Rotterdam falls below R2 after a target price has become stale, that old
target price stays excluded until the target fuel is declared again. This is
reconstructed from the daily series rather than stored as mutable state.
"""
from __future__ import annotations

import csv
import hashlib
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Mapping

OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
ENTRY_DATE_2026 = date(2026, 4, 8)
R1_SOURCE_DATES_2026 = (date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7))
EXIT_DATES_2026 = (date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2))
VALUE_COLUMN = "rotterdam_eur_l"


def _finite_float(raw: str | float, *, context: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Rotterdam value in {context}: {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"Non-finite Rotterdam value in {context}: {raw!r}")
    return value


def read_observed(path: str | Path = OBSERVED_FILE) -> dict[date, float]:
    values: dict[date, float] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"date", VALUE_COLUMN}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"UFIP observed CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date = (row.get("date") or "").strip()
            raw_value = (row.get(VALUE_COLUMN) or "").strip()
            if raw_date and raw_value:
                day = date.fromisoformat(raw_date[:10])
                values[day] = _finite_float(raw_value, context=f"observed {day}")
    if not values:
        raise ValueError("UFIP observed CSV contains no usable Rotterdam Gazole value")
    return dict(sorted(values.items()))


def mean_on_dates(observations: Mapping[date, float], dates: tuple[date, ...]) -> float:
    missing = [d for d in dates if d not in observations]
    if missing:
        raise ValueError("Missing observed UFIP quotations for calibration dates: " + ", ".join(map(str, missing)))
    return mean(_finite_float(observations[d], context=f"calibration {d}") for d in dates)


def calibration_2026(path: str | Path = OBSERVED_FILE) -> dict:
    observations = read_observed(path)
    # The A4C calibration dates are frozen. A later retrospective UFIP insertion
    # must not silently change R1 or the published k.
    r1 = mean_on_dates(observations, R1_SOURCE_DATES_2026)
    r2 = mean_on_dates(observations, EXIT_DATES_2026)
    k = r2 / r1
    return {
        "status": "candidate_2026_inactive",
        "territory": "corsica",
        "entry_date": ENTRY_DATE_2026.isoformat(),
        "r1_observation_count": len(R1_SOURCE_DATES_2026),
        "r1": r1,
        "r1_source_dates": [d.isoformat() for d in R1_SOURCE_DATES_2026],
        "exit_source_dates": [d.isoformat() for d in EXIT_DATES_2026],
        "k": k,
        "r2": r2,
    }


def read_daily_values(path: str | Path = DAILY_FILE) -> dict[date, float]:
    values: dict[date, float] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"date", VALUE_COLUMN}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"UFIP daily CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date = (row.get("date") or "").strip()
            raw_value = (row.get(VALUE_COLUMN) or "").strip()
            if raw_date and raw_value:
                day = date.fromisoformat(raw_date[:10])
                values[day] = _finite_float(raw_value, context=f"daily {day}")
    return values


def admissible_since(
    start_day: date,
    end_day: date,
    *,
    observed_file: str | Path = OBSERVED_FILE,
    daily_file: str | Path = DAILY_FILE,
) -> bool:
    """Persistent R2 guard from J+45 through the calculation day.

    True means Rotterdam never went below R2 over the complete calendar window.
    A single day below R2 makes the old price ineligible for the rest of that
    declaration's life. The next target-fuel declaration changes the caller's
    J+45 start_day and therefore resets this guard naturally.
    """
    if end_day < start_day:
        raise ValueError("end_day must be >= start_day")
    values = read_daily_values(daily_file)
    r2 = float(calibration_2026(observed_file)["r2"])
    d = start_day
    while d <= end_day:
        if d not in values:
            raise ValueError(f"Missing Rotterdam daily value for {d.isoformat()}")
        if values[d] < r2:
            return False
        d += timedelta(days=1)
    return True


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shared_metadata(
    observed_file: str | Path = OBSERVED_FILE,
    daily_file: str | Path = DAILY_FILE,
) -> dict:
    observed_path = Path(observed_file)
    daily_path = Path(daily_file)
    if not observed_path.exists() or not daily_path.exists():
        raise FileNotFoundError("C1 shared Rotterdam files must exist before shared snapshot export")
    return {
        "provider": "UFIP",
        "download_owner": "FredericP555/carburantscorse1",
        "single_download": True,
        "observed_asset": observed_path.name,
        "observed_sha256": _sha256(observed_path),
        "daily_asset": daily_path.name,
        "daily_sha256": _sha256(daily_path),
        "value_column": VALUE_COLUMN,
        "corsica_calibration": calibration_2026(observed_path),
        "runtime_rule": "after normal 45-day expiry, any Rotterdam day below R2 excludes the stale double-cap price until the target fuel is declared again; R2 does not define shield effectiveness",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(shared_metadata(), ensure_ascii=False, indent=2))
