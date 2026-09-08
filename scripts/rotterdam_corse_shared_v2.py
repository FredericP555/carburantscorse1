#!/usr/bin/env python3
"""Canonical prepared Corsica Rotterdam calibration produced upstream by C1.

C1 owns the single UFIP download. R2 is an admissibility threshold for stale station prices in
the double-cap case; it never defines whether the shield itself is effective. The upstream UFIP
series is explicitly contracted as Rotterdam Gazole in EUR/L, Thomson-Reuters, 5-day moving
average; those semantics are carried in the shared manifest consumed by C2.
"""
from __future__ import annotations

import csv
import hashlib
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
import sys
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.ufip import ROTTERDAM_REFERENCE_SOURCE, ROTTERDAM_SMOOTHING, ROTTERDAM_UNIT

OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
BASELINE_ENTRY_DATE_2026 = date(2026, 4, 8)
BASELINE_R1_SOURCE_DATES_2026 = (date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7))
BASELINE_EXIT_DATES_2026 = (date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2))
R1_OBSERVATION_COUNT = 3
VALUE_COLUMN = "rotterdam_eur_l"

ENTRY_DATE_2026 = BASELINE_ENTRY_DATE_2026
R1_SOURCE_DATES_2026 = BASELINE_R1_SOURCE_DATES_2026
EXIT_DATES_2026 = BASELINE_EXIT_DATES_2026


def _finite_float(raw: str | float, *, context: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Rotterdam value in {context}: {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Non-finite/non-positive Rotterdam value in {context}: {raw!r}")
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


def last_observed_before(observations: Mapping[date, float], entry_date: date, count: int = R1_OBSERVATION_COUNT) -> tuple[tuple[date, float], ...]:
    if count <= 0:
        raise ValueError("count must be > 0")
    rows = sorted((d, _finite_float(v, context=f"observed {d}")) for d, v in observations.items() if d < entry_date)
    if len(rows) < count:
        raise ValueError(f"Need {count} observed UFIP quotations before {entry_date}, found {len(rows)}")
    return tuple(rows[-count:])


def calibration_2026(path: str | Path = OBSERVED_FILE) -> dict:
    observations = read_observed(path)
    baseline_r1 = mean_on_dates(observations, BASELINE_R1_SOURCE_DATES_2026)
    baseline_r2 = mean_on_dates(observations, BASELINE_EXIT_DATES_2026)
    k = baseline_r2 / baseline_r1
    return {
        "status": "candidate_2026_inactive",
        "role": "baseline_k_calibration",
        "territory": "corsica",
        "entry_date": BASELINE_ENTRY_DATE_2026.isoformat(),
        "r1_observation_count": len(BASELINE_R1_SOURCE_DATES_2026),
        "r1": baseline_r1,
        "r1_source_dates": [d.isoformat() for d in BASELINE_R1_SOURCE_DATES_2026],
        "exit_source_dates": [d.isoformat() for d in BASELINE_EXIT_DATES_2026],
        "k": k,
        "r2": baseline_r2,
    }


def calibration_for_phase(phase_started_on: date, path: str | Path = OBSERVED_FILE) -> dict:
    observations = read_observed(path)
    baseline = calibration_2026(path)
    r1_rows = last_observed_before(observations, phase_started_on)
    r1 = mean(v for _, v in r1_rows)
    k = float(baseline["k"])
    return {
        "territory": "corsica",
        "phase_started_on": phase_started_on.isoformat(),
        "r1_observation_count": R1_OBSERVATION_COUNT,
        "r1": r1,
        "r1_source_dates": [d.isoformat() for d, _ in r1_rows],
        "k": k,
        "r2": k * r1,
        "k_source": "baseline_2026",
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


def admissible_since(start_day: date, end_day: date, *, phase_started_on: date, observed_file: str | Path = OBSERVED_FILE, daily_file: str | Path = DAILY_FILE) -> bool:
    if end_day < start_day:
        raise ValueError("end_day must be >= start_day")
    if phase_started_on > start_day:
        raise ValueError("stale-price window starts before current shield phase")
    values = read_daily_values(daily_file)
    r2 = float(calibration_for_phase(phase_started_on, observed_file)["r2"])
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


def shared_metadata(observed_file: str | Path = OBSERVED_FILE, daily_file: str | Path = DAILY_FILE) -> dict:
    observed_path = Path(observed_file)
    daily_path = Path(daily_file)
    if not observed_path.exists() or not daily_path.exists():
        raise FileNotFoundError("C1 shared Rotterdam files must exist before shared snapshot export")
    return {
        "provider": "UFIP / Energies et Mobilites",
        "reference_source": ROTTERDAM_REFERENCE_SOURCE,
        "unit": ROTTERDAM_UNIT,
        "smoothing": ROTTERDAM_SMOOTHING,
        "series": "Rotterdam Gazole quotation",
        "method_note": "UFIP public custom-value page: Rotterdam quotations in EUR/litre, source Thomson-Reuters, 5-day moving averages; no tonne/litre conversion is applied by A4C",
        "download_owner": "FredericP555/carburantscorse1",
        "single_download": True,
        "observed_asset": observed_path.name,
        "observed_sha256": _sha256(observed_path),
        "daily_asset": daily_path.name,
        "daily_sha256": _sha256(daily_path),
        "value_column": VALUE_COLUMN,
        "corsica_calibration": calibration_2026(observed_path),
        "runtime_r2_rule": {
            "k_policy": "k calibrated from the 2026 reference episode and then held constant",
            "r1_policy": "mean of the last 3 actually observed Rotterdam quotations before each effective-shield cap phase",
            "r2_formula": "R2 = k * phase_R1",
        },
        "runtime_rule": "after normal 45-day expiry, any Rotterdam day below the R2 of the current effective-shield cap phase excludes the stale double-cap price until the target fuel is declared again; R2 does not define shield effectiveness",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(shared_metadata(), ensure_ascii=False, indent=2))
