#!/usr/bin/env python3
"""Validate the complete C1 -> C2 shared bundle before publishing a release.

This runs on every selected weekly cycle, including official-data no-op weeks.
It validates integrity *and* the business contract needed by C2.
"""
from __future__ import annotations

from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path

from rotterdam_corse_shared_v2 import (
    ENTRY_DATE_2026,
    EXIT_DATES_2026,
    R1_SOURCE_DATES_2026,
)

META = Path("outputs/shared/official_13_20.meta.json")
SNAPSHOT = Path("outputs/shared/official_13_20.csv.gz")
OBSERVED = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DAILY = Path("outputs/ufip/rotterdam_gazole_daily.csv")
BRANDS = Path("config/corse_station_brands.json")
CALIBRATION_ABS_TOLERANCE = 1e-9


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_positive(value, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid {name}: {value!r}") from exc
    if not math.isfinite(result) or result <= 0:
        raise RuntimeError(f"Non-finite/non-positive {name}: {value!r}")
    return result


def validate_phases(bouclier: dict) -> None:
    for fuel in ("Gazole", "SP95"):
        fuel_meta = bouclier.get(fuel)
        if not isinstance(fuel_meta, dict) or not isinstance(fuel_meta.get("phases"), list):
            raise RuntimeError(f"Missing cap phases for {fuel}")
        parsed = []
        ids = set()
        for item in fuel_meta["phases"]:
            try:
                start = date.fromisoformat(str(item["d1"]))
                end = date.fromisoformat(str(item["d2"]))
                cap = finite_positive(item["cap"], f"{fuel} cap")
                phase_id = str(item["phase_id"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid cap phase for {fuel}") from exc
            if end < start or not phase_id or phase_id in ids:
                raise RuntimeError(f"Invalid/duplicate cap phase for {fuel}: {item!r}")
            ids.add(phase_id)
            parsed.append((start, end, cap, phase_id))
        parsed.sort()
        for previous, current in zip(parsed, parsed[1:]):
            if current[0] <= previous[1]:
                raise RuntimeError(f"Overlapping cap phases for {fuel}")


def main() -> None:
    for path in (META, SNAPSHOT, OBSERVED, DAILY, BRANDS):
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"Required shared asset missing/empty: {path}")

    meta = json.loads(META.read_text(encoding="utf-8"))
    if meta.get("schema") != "a4c-official-13-20-v1":
        raise RuntimeError("Unexpected shared snapshot schema")
    if sha256(SNAPSHOT) != meta.get("sha256"):
        raise RuntimeError("Shared snapshot SHA mismatch")
    if not {"13", "20"}.issubset({str(x) for x in meta.get("departments", [])}):
        raise RuntimeError("Shared snapshot misses department 13 or 20")
    if not {"Gazole", "SP95", "E10"}.issubset(set(meta.get("fuels", []))):
        raise RuntimeError("Shared snapshot misses a required fuel")
    with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as fh:
        if not fh.readline().strip():
            raise RuntimeError("Shared snapshot gzip has no CSV header")

    rotterdam = meta.get("rotterdam")
    if not isinstance(rotterdam, dict) or rotterdam.get("single_download") is not True:
        raise RuntimeError("Invalid Rotterdam shared metadata")
    if sha256(OBSERVED) != rotterdam.get("observed_sha256"):
        raise RuntimeError("Rotterdam observed SHA mismatch")
    if sha256(DAILY) != rotterdam.get("daily_sha256"):
        raise RuntimeError("Rotterdam daily SHA mismatch")

    calibration = rotterdam.get("corsica_calibration")
    if not isinstance(calibration, dict) or calibration.get("territory") != "corsica":
        raise RuntimeError("Missing Corsica Rotterdam calibration")
    if date.fromisoformat(str(calibration.get("entry_date"))) != ENTRY_DATE_2026:
        raise RuntimeError("Unexpected Corsica calibration entry date")
    r1_dates = tuple(date.fromisoformat(str(x)) for x in calibration.get("r1_source_dates", []))
    exit_dates = tuple(date.fromisoformat(str(x)) for x in calibration.get("exit_source_dates", []))
    if r1_dates != R1_SOURCE_DATES_2026 or exit_dates != EXIT_DATES_2026:
        raise RuntimeError("Unexpected Corsica calibration source dates")
    r1 = finite_positive(calibration.get("r1"), "Corsica R1")
    k = finite_positive(calibration.get("k"), "Corsica k")
    r2 = finite_positive(calibration.get("r2"), "Corsica R2")
    if not math.isclose(r1 * k, r2, rel_tol=0.0, abs_tol=CALIBRATION_ABS_TOLERANCE):
        raise RuntimeError("Corsica calibration invariant R1*k=R2 is broken")

    brands_meta = meta.get("corse_station_brands")
    brands_payload = json.loads(BRANDS.read_text(encoding="utf-8"))
    if not isinstance(brands_meta, dict) or brands_payload.get("schema") != "a4c-corsica-station-brands-v2":
        raise RuntimeError("Invalid Corsica brand registry contract")
    if sha256(BRANDS) != brands_meta.get("sha256"):
        raise RuntimeError("Corsica brand registry SHA mismatch")
    if not isinstance(brands_payload.get("stations"), dict) or not brands_payload["stations"]:
        raise RuntimeError("Corsica brand registry contains no stations")

    bouclier = meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Missing effective-shield metadata")
    validate_phases(bouclier)
    print("Shared C1 -> C2 release contract: OK")


if __name__ == "__main__":
    main()
