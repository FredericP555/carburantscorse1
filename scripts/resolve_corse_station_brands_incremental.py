#!/usr/bin/env python3
"""Incrementally maintain the Corsica station-brand registry.

The annual official price stock supplies the station IDs. New/unresolved IDs are always queried
on the official station page. Resolved active IDs are also reverified on a bounded schedule so a
stable station ID cannot keep a stale brand forever. Brand changes are temporal: the previous
classification is closed the day before the new verification and remains available in
``brand_history``. Published historical price series are never rewritten by this resolver.
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
BRAND_REVERIFY_DAYS = 90
BRAND_REVERIFY_LIMIT = 12


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
        return {"schema": "a4c-corsica-station-brands-v2", "stations": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("stations"), dict):
        raise RuntimeError(f"Invalid station registry: {path}")
    return payload


def ids_to_resolve(current_ids: set[str], stations: dict[str, dict]) -> list[str]:
    """Backward-compatible helper: only new/unresolved active IDs."""
    result = []
    for station_id in sorted(current_ids):
        entry = stations.get(station_id)
        if not entry or not str(entry.get("enseigne") or "").strip() or entry.get("segment") == "inconnu":
            result.append(station_id)
    return result


def _verified_day(entry: dict) -> date | None:
    raw = str(entry.get("verified_at") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def ids_to_fetch(
    current_ids: set[str],
    stations: dict[str, dict],
    *,
    today: date | None = None,
    reverify_days: int = BRAND_REVERIFY_DAYS,
    limit: int = BRAND_REVERIFY_LIMIT,
) -> list[str]:
    """Return new/unresolved/returning IDs plus a bounded oldest-first stale recheck set."""
    today = today or date.today()
    mandatory: set[str] = set(ids_to_resolve(current_ids, stations))
    stale: list[tuple[date, str]] = []
    for station_id in sorted(current_ids):
        entry = stations.get(station_id)
        if not entry:
            continue
        if not bool(entry.get("active", True)):
            mandatory.add(station_id)
            continue
        if station_id in mandatory:
            continue
        verified = _verified_day(entry)
        if verified is None or (today - verified).days >= reverify_days:
            stale.append((verified or date.min, station_id))
    stale.sort(key=lambda item: (item[0], item[1]))
    selected_stale = [station_id for _verified, station_id in stale[: max(0, int(limit))]]
    return sorted(mandatory) + [sid for sid in selected_stale if sid not in mandatory]


def _apply_explicit_corrections(
    station_id: str,
    entry: dict,
    by_id: dict[str, dict],
    by_brand: dict[str, dict],
) -> bool:
    brand = str(entry.get("enseigne") or "")
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


def _historical_brand_record(entry: dict, *, valid_to: date) -> dict | None:
    brand = str(entry.get("enseigne") or "").strip()
    if not brand and entry.get("segment") in {None, "", "inconnu"}:
        return None
    valid_from = str(entry.get("brand_valid_from") or entry.get("first_seen") or "").strip()
    if not valid_from:
        return None
    return {
        "enseigne": brand,
        "segment": entry.get("segment") or "inconnu",
        "detail": entry.get("detail") or "inconnu",
        "classification_source": entry.get("classification_source") or "auto",
        "brand_source": entry.get("brand_source") or "officiel",
        "valid_from": valid_from,
        "valid_to": valid_to.isoformat(),
        "verified_at": entry.get("verified_at") or "",
    }


def _resolved_entry(
    station_id: str,
    old: dict,
    brand: str,
    *,
    by_id: dict[str, dict],
    by_brand: dict[str, dict],
    today: date,
    now: datetime,
) -> dict:
    segment, detail, classification_source = classify_station(station_id, brand, by_id, by_brand)
    history = [dict(item) for item in (old.get("brand_history") or []) if isinstance(item, dict)]
    old_identity = (
        str(old.get("enseigne") or "").strip(),
        str(old.get("segment") or ""),
        str(old.get("detail") or ""),
        str(old.get("classification_source") or ""),
    )
    new_identity = (brand.strip(), segment, detail, classification_source)
    if old and old_identity != new_identity:
        previous = _historical_brand_record(old, valid_to=today - timedelta(days=1))
        if previous is not None:
            history.append(previous)
        valid_from = today.isoformat()
    else:
        valid_from = str(old.get("brand_valid_from") or old.get("first_seen") or today.isoformat())

    return {
        "enseigne": brand,
        "segment": segment,
        "detail": detail,
        "classification_source": classification_source,
        "brand_source": "officiel",
        "active": True,
        "first_seen": old.get("first_seen") or today.isoformat(),
        "last_seen": today.isoformat(),
        "verified_at": now.isoformat(),
        "brand_valid_from": valid_from,
        "brand_history": history,
    }


def resolve_incremental(
    registry: dict,
    current_ids: set[str],
    corrections_path: Path,
    *,
    fetcher: Callable[[str], tuple[str | None, str | None]] = fetch_brand,
    today: date | None = None,
    now: datetime | None = None,
    reverify_days: int = BRAND_REVERIFY_DAYS,
    reverify_limit: int = BRAND_REVERIFY_LIMIT,
) -> tuple[dict, dict]:
    stations = {str(k): dict(v) for k, v in (registry.get("stations") or {}).items()}
    by_id, by_brand = load_corrections(corrections_path)
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    pending = ids_to_fetch(
        current_ids,
        stations,
        today=today,
        reverify_days=reverify_days,
        limit=reverify_limit,
    )

    def fetch_one(station_id: str):
        return station_id, fetcher(station_id)

    fetched: dict[str, tuple[str | None, str | None]] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(pending))) as executor:
            fetched = dict(executor.map(fetch_one, pending))

    changed = False
    errors: dict[str, str] = {}

    for station_id, entry in stations.items():
        should_be_active = station_id in current_ids
        if bool(entry.get("active")) != should_be_active:
            entry["active"] = should_be_active
            changed = True
        if _apply_explicit_corrections(station_id, entry, by_id, by_brand):
            changed = True

    for station_id in pending:
        old = stations.get(station_id, {})
        brand, error = fetched.get(station_id, (None, "not fetched"))
        if brand:
            new_entry = _resolved_entry(
                station_id,
                old,
                brand,
                by_id=by_id,
                by_brand=by_brand,
                today=today,
                now=now,
            )
        elif str(old.get("enseigne") or "").strip() and old.get("segment") != "inconnu":
            # A transient reread failure must not erase a previously verified identity.
            errors[station_id] = error or "official brand unavailable during reverification"
            new_entry = dict(old)
            new_entry["active"] = True
            new_entry["last_seen"] = today.isoformat()
        else:
            errors[station_id] = error or "official brand unavailable"
            new_entry = {
                "enseigne": old.get("enseigne") or "",
                "segment": "inconnu",
                "detail": "inconnu",
                "classification_source": old.get("classification_source") or "auto",
                "brand_source": "non_resolu",
                "active": True,
                "first_seen": old.get("first_seen") or today.isoformat(),
                "last_seen": today.isoformat(),
                "verified_at": old.get("verified_at") or "",
                "brand_valid_from": old.get("brand_valid_from") or today.isoformat(),
                "brand_history": list(old.get("brand_history") or []),
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
            "enseigne": "official prix-carburants.gouv.fr station detail HTML",
            "note": "New/unresolved/returning IDs are queried immediately; resolved active IDs are reverified oldest-first on a bounded 90-day policy. Brand changes are prospective and previous periods remain in brand_history.",
        },
        "classification": {
            "segments": ["gms_lowcost", "traditionnel", "inconnu"],
            "unknown_policy": "inconnu is excluded from network comparisons",
            "corrections_file": str(corrections_path.relative_to(ROOT)) if corrections_path.is_relative_to(ROOT) else str(corrections_path),
            "brand_reverify_days": reverify_days,
            "brand_reverify_limit_per_run": reverify_limit,
            "temporal_policy": "a detected brand/classification change becomes valid on its verification date; earlier periods are preserved",
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
        result["generated_at"] = now.isoformat()

    summary = {
        "changed": changed,
        "current_station_count": len(current_ids),
        "known_before": len(registry.get("stations") or {}),
        "brand_fetch_count": len(pending),
        "resolved_this_run": sum(1 for sid in pending if fetched.get(sid, (None, None))[0]),
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
