#!/usr/bin/env python3
"""Export the official 13/20 observations consumed by carburantscorse2.

This runs inside the carburantscorse1 workflow and exports raw official declarations only;
it never applies c1's forward-fill or aggregation rules to the shared snapshot.

The same manifest binds together the official snapshot, the single UFIP Rotterdam Gazole
download owned by C1, the canonical prepared Corsica calibration, explicit effective-shield
cap phases, and the canonical Corsica station-brand registry. C2 can therefore pin one C1
release and consume a coherent set.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import update_data_v2 as core
import bouclier_detector
import rotterdam_corse_shared_v2
import shield_phase_v2

DEPARTMENTS = {"13", "20"}
FUELS = {"Gazole", "SP95", "E10"}
PRICE_MIN = 1.10
PRICE_MAX = 3.00
SCHEMA = "a4c-official-13-20-v1"
BRAND_REGISTRY_SCHEMA = "a4c-corsica-station-brands-v2"
BRAND_REGISTRY_PATH = Path("config/corse_station_brands.json")
BRAND_REGISTRY_ASSET = "corse_station_brands.json"
FIELDS = [
    "source_year", "station_id", "department", "cp", "city", "address", "pop",
    "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "timestamp", "date",
    "price", "price_in_reference_band",
]


def department_from_cp(cp: str) -> str | None:
    cp = (cp or "").strip()
    if len(cp) != 5 or not cp.isdigit():
        return None
    if cp.startswith("20"):
        return "20"
    return cp[:2]


def child_text(elem: ET.Element, tag: str) -> str:
    for child in list(elem):
        if child.tag.rsplit("}", 1)[-1] == tag:
            return (child.text or "").strip()
    return ""


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def parse_float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def iter_rows(year: int):
    raw = core.download(year)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not name:
            raise RuntimeError(f"Official ZIP {year} contains no XML")
        with zf.open(name) as fh:
            for _event, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag.rsplit("}", 1)[-1] != "pdv":
                    continue
                attrs = elem.attrib
                cp = (attrs.get("cp") or "").strip()
                department = department_from_cp(cp)
                if department not in DEPARTMENTS:
                    elem.clear()
                    continue

                station_id = attrs.get("id", "")
                pop = attrs.get("pop", "")
                address = child_text(elem, "adresse")
                city = child_text(elem, "ville")
                latitude = attrs.get("latitude", "")
                longitude = attrs.get("longitude", "")

                for child in list(elem):
                    if child.tag.rsplit("}", 1)[-1] != "prix":
                        continue
                    fuel = child.attrib.get("nom", "")
                    if fuel not in FUELS:
                        continue
                    ts = parse_timestamp(child.attrib.get("maj"))
                    if ts is None:
                        continue
                    price = parse_float(child.attrib.get("valeur"))
                    yield {
                        "source_year": year,
                        "station_id": station_id,
                        "department": department,
                        "cp": cp,
                        "city": city,
                        "address": address,
                        "pop": pop,
                        "is_motorway": pop == "A",
                        "latitude": latitude,
                        "longitude": longitude,
                        "fuel_id": child.attrib.get("id", ""),
                        "fuel": fuel,
                        "timestamp": ts.isoformat(),
                        "date": ts.date().isoformat(),
                        "price": price,
                        "price_in_reference_band": price is not None and PRICE_MIN <= price <= PRICE_MAX,
                    }
                elem.clear()


def parse_years(raw: str) -> list[int]:
    values = [int(x.strip()) for x in raw.split(",") if x.strip()]
    if not values:
        raise ValueError("At least one year is required")
    return sorted(set(values))


def default_years(day: date | None = None) -> list[int]:
    """Return the rolling N-1/N annual window used by the shared c1 -> c2 snapshot."""
    day = day or date.today()
    return [day.year - 1, day.year]


def brand_registry_metadata(path: Path = BRAND_REGISTRY_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Canonical Corsica brand registry missing: {path}")
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema") != BRAND_REGISTRY_SCHEMA:
        raise RuntimeError(f"Unexpected Corsica brand registry schema: {payload.get('schema')!r}")
    stations = payload.get("stations")
    if not isinstance(stations, dict) or not stations:
        raise RuntimeError("Canonical Corsica brand registry contains no stations")
    return {
        "asset": BRAND_REGISTRY_ASSET,
        "schema": BRAND_REGISTRY_SCHEMA,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "station_count": len(stations),
        "generated_at": payload.get("generated_at"),
    }


def main() -> None:
    default_year_arg = ",".join(str(year) for year in default_years())
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default=default_year_arg)
    parser.add_argument("--output", default="outputs/shared/official_13_20.csv.gz")
    parser.add_argument("--meta", default="outputs/shared/official_13_20.meta.json")
    args = parser.parse_args()

    years = parse_years(args.years)
    output = Path(args.output)
    meta_path = Path(args.meta)
    output.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    min_date = None
    max_date = None
    by_department = Counter()
    by_fuel = Counter()
    by_year = Counter()

    with gzip.open(output, "wt", encoding="utf-8", newline="", compresslevel=9) as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for year in years:
            for row in iter_rows(year):
                writer.writerow({key: row.get(key, "") for key in FIELDS})
                count += 1
                d = row["date"]
                min_date = d if min_date is None or d < min_date else min_date
                max_date = d if max_date is None or d > max_date else max_date
                by_department[row["department"]] += 1
                by_fuel[row["fuel"]] += 1
                by_year[str(year)] += 1

    if count == 0:
        raise RuntimeError("Shared snapshot is empty")
    missing_departments = DEPARTMENTS - set(by_department)
    if missing_departments:
        raise RuntimeError(f"Shared snapshot misses departments: {sorted(missing_departments)}")
    if "Gazole" not in by_fuel or "SP95" not in by_fuel or "E10" not in by_fuel:
        raise RuntimeError(f"Shared snapshot misses a required fuel: {dict(by_fuel)}")

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    bouclier = shield_phase_v2.with_cap_phases(bouclier_detector.metadata(max(years)))
    metadata = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "departments": sorted(DEPARTMENTS),
        "fuels": sorted(FUELS),
        "rows": count,
        "min_date": min_date,
        "max_date": max_date,
        "rows_by_year": dict(sorted(by_year.items())),
        "rows_by_department": dict(sorted(by_department.items())),
        "rows_by_fuel": dict(sorted(by_fuel.items())),
        "sha256": digest,
        "asset": output.name,
        "producer": "FredericP555/carburantscorse1",
        "method": "raw official declarations only; no c1 forward-fill or aggregation",
        "bouclier": bouclier,
        "rotterdam": rotterdam_corse_shared_v2.shared_metadata(),
        "corse_station_brands": brand_registry_metadata(),
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"Shared snapshot size: {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
