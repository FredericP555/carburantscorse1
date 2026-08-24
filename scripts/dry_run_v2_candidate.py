#!/usr/bin/env python3
"""Real-data V2 threshold dry-run for carburantscorse1.

PREP ONLY. This script never writes data.json and never publishes Pages. It rebuilds
station/day eligibility from the official annual stock, calls the prepared
``reliability_policy_v2.evaluate()`` and ``r2_guard_v2.stale_price_admissible()``
on real 2026 observations, and compares the result with the currently published
45-day C1 behaviour.

The retrospective simulation is intentionally limited to 2026 for now. Extending
R2 to 2023-2025 requires an explicit historical Rotterdam input for each shield
episode; 2022 is never treated as an effective-shield year.
"""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap
import bouclier_detector
import r2_guard_v2
import reliability_policy_v2
import shield_phase_v2
import update_data_v2 as core

ROOT = Path(__file__).resolve().parents[1]
MAIN_DATA_URL = "https://raw.githubusercontent.com/FredericP555/carburantscorse1/main/data.json"
CORSE_REGISTRY = ROOT / "config" / "corse_station_brands.json"
ROTTERDAM_OBSERVED = ROOT / "outputs" / "ufip" / "rotterdam_gazole_observed.csv"
TARGET_FUELS = ("Gazole", "SP95")
TARGET_SHORT = {"Gazole": "Gazole", "SP95": "SP95"}
ALL_MAINLAND_REGIONS = tuple(core.REGIONS)
CURRENT_MAX_AGE_DAYS_INCLUSIVE = core.MAX_FFILL_DAYS


def _finite_float(raw) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _load_main_payload() -> tuple[dict | None, dict]:
    try:
        req = urllib.request.Request(MAIN_DATA_URL, headers={"User-Agent": "A4C-c1-v2-dry-run/1.0"})
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        origin = date.fromisoformat(str(payload["origin"]))
        offsets = []
        for short in ("G", "S"):
            for region in ("corse", "moy_regions"):
                rows = (((payload.get(short) or {}).get(region) or {}).get("d") or [])
                offsets.extend(int(row[0]) for row in rows if isinstance(row, list) and row)
        if not offsets:
            raise ValueError("main data.json has no daily offsets")
        last = origin + timedelta(days=max(offsets))
        return payload, {
            "source": "main-data.json",
            "last_published_day": last.isoformat(),
            "switch_date": (last + timedelta(days=1)).isoformat(),
        }
    except Exception as exc:
        return None, {"source": "fallback", "error": f"{type(exc).__name__}: {exc}"}


def _read_registry() -> dict:
    payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    stations = payload.get("stations")
    if not isinstance(stations, dict) or not stations:
        raise RuntimeError("Corsica station-brand registry is missing or empty")
    return stations


def _parse_official_events(start_day: date, end_day: date):
    """Return target price declarations and all-fuel activity declarations.

    Target prices preserve explicit invalid declarations as ``None`` so they stop a
    previous price, matching the current C1 numerical core. All-fuel activity is used
    only as evidence that a mainland station has declared another fuel recently.
    """
    target: dict[tuple[str, str], dict[str, list[tuple[datetime, float | None]]]] = defaultdict(lambda: defaultdict(list))
    activity: dict[tuple[str, str], dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
    rows = Counter()

    for year in range(start_day.year - 1, end_day.year + 1):
        raw = core.download(year)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
            if not name:
                raise RuntimeError(f"Official ZIP {year} contains no XML")
            with zf.open(name) as fh:
                for _event, elem in ET.iterparse(fh, events=("end",)):
                    if elem.tag.rsplit("}", 1)[-1] != "pdv":
                        continue
                    if elem.attrib.get("pop") == "A":
                        elem.clear()
                        continue
                    region = core.region_from_cp(elem.attrib.get("cp", ""))
                    if region is None:
                        elem.clear()
                        continue
                    sid = str(elem.attrib.get("id") or "").strip()
                    if not sid:
                        elem.clear()
                        continue
                    station_key = (sid, region)
                    for child in list(elem):
                        if child.tag.rsplit("}", 1)[-1] != "prix":
                            continue
                        fuel = str(child.attrib.get("nom") or "").strip()
                        if not fuel:
                            continue
                        try:
                            ts = datetime.fromisoformat(child.attrib["maj"])
                        except (KeyError, ValueError):
                            continue
                        if ts.date() > end_day:
                            continue
                        activity[station_key][fuel].append(ts)
                        rows["activity"] += 1
                        if fuel in TARGET_FUELS:
                            raw_value = _finite_float(child.attrib.get("valeur"))
                            value = raw_value if raw_value is not None and core.PRICE_MIN <= raw_value <= core.PRICE_MAX else None
                            target[station_key][fuel].append((ts, value))
                            rows[f"target_{fuel}"] += 1
                    elem.clear()

    for fuels in target.values():
        for values in fuels.values():
            values.sort(key=lambda item: item[0])
    for fuels in activity.values():
        for values in fuels.values():
            values.sort()
    return target, activity, dict(rows)


def _phase_maps(bouclier: dict, start_day: date, end_day: date):
    phases = shield_phase_v2.phases_from_bouclier_metadata(bouclier)
    result = {fuel: {} for fuel in TARGET_FUELS}
    for fuel in TARGET_FUELS:
        for phase in phases.get(fuel, []):
            d = max(start_day, phase.started_on)
            stop = min(end_day, phase.ended_on)
            while d <= stop:
                result[fuel][d] = phase
                d += timedelta(days=1)
    return result


def _published_gaps(payload: dict | None) -> dict[str, dict[date, float]]:
    if not payload:
        return {}
    origin = date.fromisoformat(str(payload["origin"]))
    output = {}
    for fuel, short in (("Gazole", "G"), ("SP95", "S")):
        corse_rows = (((payload.get(short) or {}).get("corse") or {}).get("d") or [])
        main_rows = (((payload.get(short) or {}).get("moy_regions") or {}).get("d") or [])
        corse = {origin + timedelta(days=int(r[0])): float(r[2]) for r in corse_rows if len(r) >= 3 and r[2] is not None}
        mainland = {origin + timedelta(days=int(r[0])): float(r[2]) for r in main_rows if len(r) >= 3 and r[2] is not None}
        output[fuel] = {d: round((corse[d] - mainland[d]) * 100.0, 3) for d in set(corse) & set(mainland)}
    return output


def _daily_gaps(sums, counts, mode: str, start_day: date, end_day: date):
    result: dict[str, dict[date, float]] = {fuel: {} for fuel in TARGET_FUELS}
    d = start_day
    while d <= end_day:
        for fuel in TARGET_FUELS:
            corse_key = (mode, fuel, "corse", d)
            if not counts.get(corse_key):
                continue
            corse_ttc = sums[corse_key] / counts[corse_key]
            mainland_ht = []
            for region in ALL_MAINLAND_REGIONS:
                key = (mode, fuel, region, d)
                if counts.get(key):
                    mainland_ht.append((sums[key] / counts[key]) / 1.20)
            if not mainland_ht:
                continue
            corse_ht = corse_ttc / 1.13
            result[fuel][d] = (corse_ht - sum(mainland_ht) / len(mainland_ht)) * 100.0
        d += timedelta(days=1)
    return result


def _periodize(values: dict[date, float], granularity: str) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for day, value in sorted(values.items()):
        if granularity == "daily":
            key = day.isoformat()
        elif granularity == "weekly":
            key = (day - timedelta(days=day.weekday())).isoformat()
        elif granularity == "monthly":
            key = day.strftime("%Y-%m")
        else:
            raise ValueError(granularity)
        buckets[key].append(float(value))
    return {key: sum(vals) / len(vals) for key, vals in buckets.items() if vals}


def _compare(left: dict[str, float], right: dict[str, float]) -> dict:
    common = sorted(set(left) & set(right))
    changes = []
    for key in common:
        delta = right[key] - left[key]
        if abs(delta) >= 0.005:
            changes.append({
                "period": key,
                "actuel_c_l": round(left[key], 3),
                "v2_c_l": round(right[key], 3),
                "delta_c_l": round(delta, 3),
            })
    changes.sort(key=lambda item: (abs(item["delta_c_l"]), item["period"]), reverse=True)
    absolute = [abs(item["delta_c_l"]) for item in changes]
    return {
        "common_periods": len(common),
        "changed_periods": len(changes),
        "max_abs_delta_c_l": round(max(absolute), 3) if absolute else 0.0,
        "median_abs_delta_c_l": round(float(pd.Series(absolute).median()), 3) if absolute else 0.0,
        "largest_changes": changes[:12],
    }


def main() -> None:
    today = date.today()
    start_day = date(2026, 1, 1)
    end_day = min(today - timedelta(days=1), date(2026, 12, 31))
    main_payload, switch_meta = _load_main_payload()
    switch_day = date.fromisoformat(switch_meta.get("switch_date", (end_day + timedelta(days=1)).isoformat())) if switch_meta.get("switch_date") else end_day + timedelta(days=1)

    if not ROTTERDAM_OBSERVED.exists():
        raise RuntimeError("Run scripts/fetch_ufip.py before the C1 V2 dry-run")

    stations = _read_registry()
    target_events, activity_events, parse_counts = _parse_official_events(start_day, end_day)
    bouclier = shield_phase_v2.with_cap_phases(bouclier_detector.metadata(end_day.year))
    phase_map = _phase_maps(bouclier, start_day, end_day)

    sums = defaultdict(float)
    counts = defaultdict(int)
    reasons = Counter()
    changed_station_days = Counter()
    r2_calls = r2_true = r2_false = r2_unavailable = 0
    r2_errors = Counter()
    r2_cache: dict[tuple[date, date], tuple[bool | None, str | None]] = {}

    all_station_keys = sorted(set(target_events) | set(activity_events))
    for station_key in all_station_keys:
        sid, region = station_key
        fuel_targets = target_events.get(station_key, {})
        if not any(fuel_targets.get(fuel) for fuel in TARGET_FUELS):
            continue
        fuel_activity = activity_events.get(station_key, {})

        target_ptr = {fuel: 0 for fuel in TARGET_FUELS}
        target_state: dict[str, tuple[datetime, float | None] | None] = {fuel: None for fuel in TARGET_FUELS}
        activity_ptr = {fuel: 0 for fuel in fuel_activity}
        activity_state: dict[str, datetime | None] = {fuel: None for fuel in fuel_activity}

        for fuel in TARGET_FUELS:
            values = fuel_targets.get(fuel, [])
            while target_ptr[fuel] < len(values) and values[target_ptr[fuel]][0].date() < start_day:
                target_state[fuel] = values[target_ptr[fuel]]
                target_ptr[fuel] += 1
        for fuel, values in fuel_activity.items():
            while activity_ptr[fuel] < len(values) and values[activity_ptr[fuel]].date() < start_day:
                activity_state[fuel] = values[activity_ptr[fuel]]
                activity_ptr[fuel] += 1

        registry_state = classify_registry_entry(stations.get(sid)) if region == "corse" else None
        is_total = registry_state == TOTAL if region == "corse" else False
        region_kind = "corsica" if region == "corse" else "mainland"

        d = start_day
        while d <= end_day:
            for fuel in TARGET_FUELS:
                values = fuel_targets.get(fuel, [])
                j = target_ptr[fuel]
                while j < len(values) and values[j][0].date() <= d:
                    target_state[fuel] = values[j]
                    j += 1
                target_ptr[fuel] = j
            for fuel, values in fuel_activity.items():
                j = activity_ptr[fuel]
                while j < len(values) and values[j].date() <= d:
                    activity_state[fuel] = values[j]
                    j += 1
                activity_ptr[fuel] = j

            gazole_price = target_state["Gazole"][1] if target_state["Gazole"] else None
            sp95_price = target_state["SP95"][1] if target_state["SP95"] else None
            gazole_phase = phase_map["Gazole"].get(d)
            sp95_phase = phase_map["SP95"].get(d)
            gazole_cap = gazole_phase.cap if gazole_phase else None
            sp95_cap = sp95_phase.cap if sp95_phase else None
            activity_by_fuel = {fuel: ts for fuel, ts in activity_state.items() if ts is not None}

            for fuel in TARGET_FUELS:
                state = target_state[fuel]
                last_declared = state[0] if state else None
                last_price = state[1] if state else None
                age = None if last_declared is None else (d - last_declared.date()).days
                current_eligible = bool(
                    last_declared is not None
                    and age is not None
                    and 0 <= age <= CURRENT_MAX_AGE_DAYS_INCLUSIVE
                    and last_price is not None
                )

                phase = phase_map[fuel].get(d)
                r2_verdict = None
                both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
                if (
                    region == "corse"
                    and is_total
                    and age is not None
                    and age >= reliability_policy_v2.NORMAL_MAX_AGE_DAYS
                    and phase is not None
                    and at_cap(last_price, phase.cap)
                    and both_capped
                ):
                    r2_calls += 1
                    cache_key = (last_declared.date(), d)
                    if cache_key not in r2_cache:
                        try:
                            value = r2_guard_v2.stale_price_admissible(
                                last_declared,
                                d,
                                bouclier_metadata=bouclier,
                            )
                            r2_cache[cache_key] = (bool(value), None)
                        except Exception as exc:
                            r2_cache[cache_key] = (None, f"{type(exc).__name__}: {exc}")
                    r2_verdict, r2_error = r2_cache[cache_key]
                    if r2_verdict is True:
                        r2_true += 1
                    elif r2_verdict is False:
                        r2_false += 1
                    else:
                        r2_unavailable += 1
                        if r2_error:
                            r2_errors[r2_error] += 1

                decision = reliability_policy_v2.evaluate(
                    day=d,
                    region_kind=region_kind,
                    target_fuel=fuel,
                    last_declared_at=last_declared,
                    last_price=last_price,
                    latest_price_valid=last_price is not None,
                    target_rupture_active=False,
                    independently_inactive=False,
                    is_total=is_total,
                    shield_effective=phase is not None,
                    applicable_cap=phase.cap if phase else None,
                    phase_started_on=phase.started_on if phase else None,
                    activity_by_fuel=activity_by_fuel,
                    gazole_price=gazole_price,
                    gazole_cap=gazole_cap,
                    sp95_price=sp95_price,
                    sp95_cap=sp95_cap,
                    rotterdam_stale_price_admissible=r2_verdict,
                )
                v2_eligible = bool(decision.eligible)
                prospective_eligible = current_eligible if d < switch_day else v2_eligible
                reasons[f"{region_kind}/{fuel}/{decision.reason}"] += 1
                if current_eligible != v2_eligible:
                    changed_station_days[f"{region_kind}/{fuel}/{current_eligible}->{v2_eligible}"] += 1

                for mode, eligible in (
                    ("ACTUEL", current_eligible),
                    ("NOUVELLE_REGLE_RETROACTIVE", v2_eligible),
                    ("NOUVELLE_REGLE_PROSPECTIVE", prospective_eligible),
                ):
                    if eligible and last_price is not None:
                        key = (mode, fuel, region, d)
                        sums[key] += float(last_price)
                        counts[key] += 1
            d += timedelta(days=1)

    daily = {
        mode: _daily_gaps(sums, counts, mode, start_day, end_day)
        for mode in ("ACTUEL", "NOUVELLE_REGLE_RETROACTIVE", "NOUVELLE_REGLE_PROSPECTIVE")
    }

    comparisons = {}
    for candidate_mode in ("NOUVELLE_REGLE_RETROACTIVE", "NOUVELLE_REGLE_PROSPECTIVE"):
        block = {}
        for fuel in TARGET_FUELS:
            for granularity in ("daily", "weekly", "monthly"):
                left = _periodize(daily["ACTUEL"][fuel], granularity)
                right = _periodize(daily[candidate_mode][fuel], granularity)
                block[f"{fuel}/{granularity}"] = _compare(left, right)
        comparisons[f"{candidate_mode}_vs_ACTUEL"] = block

    baseline_validation = {}
    published = _published_gaps(main_payload)
    for fuel in TARGET_FUELS:
        current_periodized = {d.isoformat(): v for d, v in daily["ACTUEL"][fuel].items()}
        published_periodized = {d.isoformat(): v for d, v in (published.get(fuel) or {}).items() if start_day <= d <= end_day}
        baseline_validation[fuel] = _compare(published_periodized, current_periodized)

    observed = pd.read_csv(ROTTERDAM_OBSERVED)
    ufip_last = None
    if not observed.empty and "date" in observed.columns:
        ufip_last = str(pd.to_datetime(observed["date"]).max().date())

    output = {
        "status": "dry-run-only",
        "production_modified": False,
        "window": {
            "retroactive_start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "prospective_switch_date": switch_day.isoformat(),
            "prospective_switch_source": switch_meta,
        },
        "source": {
            "official_parse_counts": parse_counts,
            "ufip_last_observed_date": ufip_last,
            "corsica_registry_station_count": len(stations),
        },
        "engine_calls": {
            "evaluate_station_days": sum(reasons.values()),
            "r2_calls": r2_calls,
            "r2_true": r2_true,
            "r2_false": r2_false,
            "r2_unavailable": r2_unavailable,
            "r2_errors": dict(r2_errors.most_common(20)),
        },
        "eligibility": {
            "reason_counts": dict(reasons.most_common()),
            "changed_station_days": dict(changed_station_days.most_common()),
        },
        "baseline_validation_against_main": baseline_validation,
        "comparison": comparisons,
        "known_reserves": [
            "the current C1 baseline intentionally reproduces its inclusive J+45 carry so the V2 J+45 boundary is measurable rather than silently rewritten",
            "rupture intervals are not yet wired into this dry-run decision input",
            "independent closure/inactivity evidence is not yet wired into this dry-run decision input",
            "pre-2026 R2 retrospective analysis is deliberately not simulated until episode-appropriate historical Rotterdam data are assembled",
            "2022 is not an effective-shield year and will never be backfilled with shield logic",
        ],
    }

    out = ROOT / "outputs" / "v2" / "c1-v2-dry-run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
