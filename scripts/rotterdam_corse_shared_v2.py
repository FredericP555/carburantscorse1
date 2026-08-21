#!/usr/bin/env python3
"""Canonical prepared Corsica Rotterdam calibration produced upstream by C1.

C1 owns the single UFIP download. This module derives the candidate Corsica
calibration metadata from that one observed series so C2 can consume the exact
same result instead of recalculating it independently.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Mapping

OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
ENTRY_DATE_2026 = date(2026, 4, 8)
R1_OBSERVATION_COUNT = 3
EXIT_DATES_2026 = (date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2))
VALUE_COLUMN = "rotterdam_eur_l"


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
                values[date.fromisoformat(raw_date[:10])] = float(raw_value)
    if not values:
        raise ValueError("UFIP observed CSV contains no usable Rotterdam Gazole value")
    return dict(sorted(values.items()))


def last_observed_before(observations: Mapping[date, float], entry_date: date, count: int) -> tuple[tuple[date, float], ...]:
    rows = sorted((d, float(v)) for d, v in observations.items() if d < entry_date)
    if len(rows) < count:
        raise ValueError(f"Need {count} observed UFIP quotations before {entry_date}, found {len(rows)}")
    return tuple(rows[-count:])


def mean_on_dates(observations: Mapping[date, float], dates: tuple[date, ...]) -> float:
    missing = [d for d in dates if d not in observations]
    if missing:
        raise ValueError("Missing observed UFIP quotations for calibration dates: " + ", ".join(map(str, missing)))
    return mean(float(observations[d]) for d in dates)


def calibration_2026(path: str | Path = OBSERVED_FILE) -> dict:
    observations = read_observed(path)
    r1_rows = last_observed_before(observations, ENTRY_DATE_2026, R1_OBSERVATION_COUNT)
    r1 = mean(v for _, v in r1_rows)
    r2 = mean_on_dates(observations, EXIT_DATES_2026)
    k = r2 / r1
    return {
        "status": "candidate_2026_inactive",
        "territory": "corsica",
        "entry_date": ENTRY_DATE_2026.isoformat(),
        "r1_observation_count": R1_OBSERVATION_COUNT,
        "r1": r1,
        "r1_source_dates": [d.isoformat() for d, _ in r1_rows],
        "exit_source_dates": [d.isoformat() for d in EXIT_DATES_2026],
        "k": k,
        "r2": r2,
    }


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
        "daily_asset": daily_path.name,
        "value_column": VALUE_COLUMN,
        "corsica_calibration": calibration_2026(observed_path),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(shared_metadata(), ensure_ascii=False, indent=2))
