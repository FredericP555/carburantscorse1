#!/usr/bin/env python3
"""Resolve only new/unresolved Corsica station IDs during the price update.

Known resolved IDs are never refetched from prix-carburants.gouv.fr. The annual official
price stock already downloaded by the weekly pipeline supplies the station IDs; only an ID
missing from the compact registry (or still unresolved) triggers one station-page lookup.

Only IDs whose latest declaration falls inside the dashboard's current 45-day carry window are
considered active. Disappeared IDs are retained in the registry for historical series and merely
marked inactive.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Callable

import update_data_v2 as core
from update_corse_station_brands import (
    DEFAULT_CORRECTIONS,
    DEFAULT_OUTPUT,
    SEGMENTS,
    _norm,
    classify_station,
    fetch_brand,
    load_corrections,
)

ROOT = Path(__file__).resolve().parents[1]
WORKERS = 4


def current_corsica_ids(year: int) -> set[str]:
    """Return IDs relevant to the current c1 carry window; reuse the workflow ZIP cache."""
    changes = core.parse_year(year)
    latest_by_station: dict[str, date] = {}
    source_dates: list[date] = []
    for (station_id, region, _fuel), values in changes.items():
        if region != "corse":
            continue
        dates = [ts.date() for ts, _value in values if ts.year == year]
        if not dates:
            continue
        latest = max(dates)
        sid = str(station_id)
        previous = latest_by_station.get(sid)
        latest_by_station[sid] = latest if previous is None else max(previous, latest)
        source_dates.append(latest)
    if not source_dates:
        raise RuntimeError(f"No Corsica station ID found in official stock for {year}")

    source_max = max(source_dates)
    cutoff = source_max - timedelta(days=core.MAX_FFILL_DAYS)
    ids = {sid for sid, latest in latest_by_station.items() if latest >= cutoff}
    if not ids:
        raise RuntimeError(f"No Corsica station ID remains inside the {core.MAX_FFILL_DAYS}-day carry window")
    return ids


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {
            "schema": "a4c-corsica-station-brands-v2",
            "stations": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("stations"), dict):
        raise RuntimeError(f"Invalid station registry: {path}")
    return payload


def ids_to_resolve(current_ids: set[str], stations: dict[str, dict]) -> list[str]:
    """Only brandless or unknown current IDs need an official station-page request."""
    result = []
    for station_id in sorted(current_ids):
        entry = stations.get(station_id)
        if not entry:
            result.append(station_id)
            continue
        if not str(entry.get("enseigne") or "").strip() or entry.get("segment") == "inconnu":
            result.append(station_id)
    return result


def _apply_explicit_corrections(
    station_id: str,
    entry: dict,
    by_id: dict[str, dict],
    by_brand: dict[str, dict],
) -> bool:
    """Apply corrections to known IDs without rerunning automatic classification."""
    brand = str(entry.get("enseigne") or "")
    # Preserve a known station's automatic classification. Only an explicit correction may
    # change it without a new station ID; station-ID correction has final priority.
    correction = None
    brand_correction = by_brand.get(_norm(brand))
    if brand_correction:
        correction = (brand_correction, "correction_marque")
    if station_id in by_id:
        correction = (by_id[station_id], "correction_id")
    if not correction:
        return False
    value, source = correction
    changed = (
        entry.get("segment") != value["segment"]
        or entry.get("detail") != value["detail"]
        or entry.get("classification_source") != source
    )
    entry["segment"] = value["segment"]
    entry["detail"] = value["detail"]
    entry["classification_source"] = source
    return changed


def resolve_incremental(
    registry: dict,
    current_ids: set[str],
    corrections_path: Path,
    *,
    fetcher: Callable[[str], tuple[str | None, str | None]] = fetch_brand,
) -> tuple[dict, dict]:
    stations = {str(k): dict(v) for k, v in (registry.get("stations") or {}).items()}
    by_id, by_brand = load_corrections(corrections_path)
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    pending = ids_to_resolve(current_ids, stations)

    def fetch_one(station_id: str):
        return station_id, fetcher(station_id)

    fetched: dict[str, tuple[str | None, str | None]] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(pending))) as executor:
            fetched = dict(executor.map(fetch_one, pending))

    changed = False
    errors: dict[str, str] = {}

    # Preserve every historical ID. Only active state and explicit corrections may change for
    # already-known resolved IDs; their official brand page is not requested again.
    for station_id, entry in stations.items():
        should_be_active = station_id in current_ids
        if bool(entry.get("active")) != should_be_active:
            entry["active"] = should_be_active
            if should_be_active:
                entry["last_seen"] = today
            changed = True
        if _apply_explicit_corrections(station_id, entry, by_id, by_brand):
            changed = True

    for station_id in pending:
        old = stations.get(station_id, {})
        brand, error = fetched.get(station_id, (None, "not fetched"))
        if brand:
            segment, detail, classification_source = classify_station(
                station_id, brand, by_id, by_brand
            )
            new_entry = {
                "enseigne": brand,
                "segment": segment,
                "detail": detail,
                "classification_source": classification_source,
                "brand_source": "officiel",
                "active": True,
                "first_seen": old.get("first_seen") or today,
                "last_seen": today,
                "verified_at": now,
            }
        else:
            errors[station_id] = error or "official brand unavailable"
            new_entry = {
                "enseigne": old.get("enseigne") or "",
                "segment": "inconnu",
                "detail": "inconnu",
                "classification_source": old.get("classification_source") or "auto",
                "brand_source": "non_resolu",
                "active": True,
                "first_seen": old.get("first_seen") or today,
                "last_seen": today,
                "verified_at": old.get("verified_at") or "",
            }
        if stations.get(station_id) != new_entry:
            stations[station_id] = new_entry
            changed = True

    active_entries = [v for sid, v in stations.items() if sid in current_ids]
    segment_counts = {
        segment: sum(1 for entry in active_entries if entry.get("segment") == segment)
        for segment in sorted(SEGMENTS)
    }
    detail_counts: dict[str, int] = {}
    for entry in active_entries:
        detail = str(entry.get("detail") or "inconnu")
        detail_counts[detail] = detail_counts.get(detail, 0) + 1

    result = dict(registry)
    result.update({
        "schema": "a4c-corsica-station-brands-v2",
        "source": {
            "station_ids": "official annual fuel-price stock already used by the A4C update",
            "enseigne": "official prix-carburants.gouv.fr station detail HTML, queried only for new/unresolved IDs",
            "note": "Known resolved IDs are not refetched; disappeared IDs remain for historical classification.",
        },
        "classification": {
            "segments": ["gms_lowcost", "traditionnel", "inconnu"],
            "unknown_policy": "inconnu is excluded from network comparisons",
            "corrections_file": str(corrections_path.relative_to(ROOT)) if corrections_path.is_relative_to(ROOT) else str(corrections_path),
        },
        "current_station_count": len(current_ids),
        "verified_brand_count": sum(1 for entry in active_entries if entry.get("enseigne")),
        "fetch_error_count": len(errors),
        "unresolved_current_count": sum(1 for entry in active_entries if entry.get("segment") == "inconnu"),
        "segment_counts_current": segment_counts,
        "detail_counts_current": dict(sorted(detail_counts.items())),
        "stations": dict(sorted(stations.items())),
    })
    if changed:
        result["generated_at"] = now

    summary = {
        "changed": changed,
        "current_station_count": len(current_ids),
        "known_before": len(registry.get("stations") or {}),
        "brand_fetch_count": len(pending),
        "resolved_this_run": len(pending) - len(errors),
        "unresolved_this_run": len(errors),
        "unresolved_ids": sorted(errors),
    }
    return result, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--year", type=int, default=date.today().year)
    args = parser.parse_args()

    registry = load_registry(args.output)
    current_ids = current_corsica_ids(args.year)
    updated, summary = resolve_incremental(registry, current_ids, args.corrections)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["changed"]:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {args.output}")
    else:
        print("No station-brand registry change; no file rewrite.")


if __name__ == "__main__":
    main()
