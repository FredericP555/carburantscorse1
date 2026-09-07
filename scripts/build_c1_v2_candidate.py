#!/usr/bin/env python3
"""Build a guarded C1 V2 production candidate without touching data.json.

Initial transition candidate:
- daily rows before 2026-07-23 remain exactly unchanged;
- the overlapping week starting 2026-07-20 remains unchanged;
- complete weekly rows switch from 2026-07-27;
- July 2026 monthly remains unchanged; monthly V2 starts in August 2026.

After ``meta.v2.active`` exists, published daily rows are immutable and only new daily
rows are appended. The current incomplete weekly/monthly buckets may be rebuilt from the
combined daily series, matching C1's established append-only aggregation behaviour.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import io
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap
import bouclier_detector
import c1_bouclier_meta
import c1_last_date
import r2_guard_v2
import reliability_policy_v2
import shield_phase_v2
import update_data_v2 as core

ROOT = Path(__file__).resolve().parents[1]
SWITCH_DAY = date(2026, 7, 23)
WEEKLY_SWITCH = date(2026, 7, 27)
MONTHLY_SWITCH = "2026-08"
TARGET_FUELS = ("Gazole", "SP95")
CORSE_REGISTRY = ROOT / "config" / "corse_station_brands.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="data.json")
    p.add_argument("--output", default="outputs/c1-v2-candidate.json")
    p.add_argument("--summary", default="outputs/c1-v2-summary.json")
    p.add_argument("--end")
    return p.parse_args()


def _timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _float(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) else None


def _fuel_name(child: ET.Element) -> str:
    return str(child.attrib.get("fuel") or child.attrib.get("nom") or "").strip()


def _event_rows(elem: ET.Element, sid: str, sink: list[tuple]) -> None:
    for child in list(elem):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag not in {"rupture", "fermeture"}:
            continue
        start = _timestamp(child.attrib.get("debut"))
        if start is None:
            continue
        end = _timestamp(child.attrib.get("fin"))
        fuel = _fuel_name(child) if tag == "rupture" else ""
        if tag == "rupture" and fuel not in TARGET_FUELS:
            continue
        sink.append((sid, tag, fuel, start, end, str(child.attrib.get("type") or "")))


def parse_year(year: int, declarations: dict, events: list[tuple], source_dates: list[date]) -> None:
    raw = core.download(year)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not name:
            raise RuntimeError(f"Official ZIP {year} contains no XML")
        with zf.open(name) as fh:
            for _, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag.rsplit("}", 1)[-1] != "pdv":
                    continue
                if elem.attrib.get("pop") == "A":
                    elem.clear(); continue
                region = core.region_from_cp(elem.attrib.get("cp", ""))
                if not region:
                    elem.clear(); continue
                sid = str(elem.attrib.get("id") or "")
                _event_rows(elem, sid, events)
                for child in list(elem):
                    if child.tag.rsplit("}", 1)[-1] != "prix":
                        continue
                    fuel = str(child.attrib.get("nom") or "").strip()
                    if not fuel:
                        continue
                    ts = _timestamp(child.attrib.get("maj"))
                    if ts is None:
                        continue
                    source_dates.append(ts.date())
                    raw_value = _float(child.attrib.get("valeur"))
                    value = raw_value if fuel in TARGET_FUELS and core.is_reliable_price(raw_value) else None
                    declarations.setdefault((sid, region, fuel), []).append((ts, value))
                elem.clear()


def _dedupe_updates(values: list[tuple[datetime, float | None]]) -> list[tuple[datetime, float | None]]:
    per_day: dict[date, tuple[datetime, float | None]] = {}
    for ts, value in sorted(values, key=lambda x: x[0]):
        per_day[ts.date()] = (ts, value)
    return sorted(per_day.values(), key=lambda x: x[0])


class EventGuard:
    def __init__(self, events: list[tuple], declarations: dict):
        self.ruptures: dict[tuple[str, str], list[tuple[date, date | None]]] = defaultdict(list)
        self.closures: dict[str, list[tuple[date, date | None]]] = defaultdict(list)
        self.stats = Counter()
        by_station_fuel: dict[tuple[str, str], list[datetime]] = defaultdict(list)
        by_station: dict[str, list[datetime]] = defaultdict(list)
        for (sid, _region, fuel), values in declarations.items():
            for ts, _value in values:
                by_station_fuel[(sid, fuel)].append(ts)
                by_station[sid].append(ts)
        for values in by_station_fuel.values(): values.sort()
        for values in by_station.values(): values.sort()
        seen = set()
        for sid, kind, fuel, started, ended, event_type in events:
            key = (sid, kind, fuel, started, ended, event_type)
            if key in seen: continue
            seen.add(key)
            end_day = ended.date() if ended else None
            if ended is not None:
                self.stats[f"{kind}_explicit_end"] += 1
            else:
                declarations_after = by_station_fuel.get((sid, fuel), []) if kind == "rupture" else by_station.get(sid, [])
                idx = bisect_right(declarations_after, started)
                if idx < len(declarations_after):
                    reopen = declarations_after[idx]
                    end_day = reopen.date() - timedelta(days=1)
                    self.stats[f"{kind}_open_closed_by_declaration"] += 1
                else:
                    self.stats[f"{kind}_open_remaining"] += 1
            if end_day is not None and end_day < started.date():
                self.stats[f"{kind}_effectively_empty"] += 1
                continue
            if kind == "rupture": self.ruptures[(sid, fuel)].append((started.date(), end_day))
            else: self.closures[sid].append((started.date(), end_day))
        # Open-ended intervals have end=None. Sort only on the start date so an
        # explicit-ended interval with the same start never compares date to None.
        for values in self.ruptures.values(): values.sort(key=lambda interval: interval[0])
        for values in self.closures.values(): values.sort(key=lambda interval: interval[0])
        self.stats["event_rows_unique"] = len(seen)

    @staticmethod
    def _active(day: date, intervals: list[tuple[date, date | None]]) -> bool:
        return any(start <= day and (end is None or day <= end) for start, end in intervals)

    def rupture_active(self, sid: str, fuel: str, day: date) -> bool:
        verdict = self._active(day, self.ruptures.get((sid, fuel), []))
        if verdict: self.stats["rupture_active_station_fuel_days"] += 1
        return verdict

    def closed(self, sid: str, day: date) -> bool:
        verdict = self._active(day, self.closures.get(sid, []))
        if verdict: self.stats["closure_active_station_days_checks"] += 1
        return verdict


def _value_at(updates: list[tuple[datetime, float | None]], pointers: dict, key, day: date):
    idx, last_ts, last_value = pointers.get(key, (0, None, None))
    while idx < len(updates) and updates[idx][0].date() <= day:
        last_ts, last_value = updates[idx]
        idx += 1
    pointers[key] = (idx, last_ts, last_value)
    return last_ts, last_value


def build_v2_daily(years: list[int], start: date, end: date) -> tuple[pd.DataFrame, dict]:
    declarations: dict = {}
    events: list[tuple] = []
    source_dates: list[date] = []
    for year in years:
        parse_year(year, declarations, events, source_dates)
    if not source_dates:
        raise RuntimeError("No official declarations parsed")
    source_max = max(source_dates)
    end = min(end, source_max)
    if end < start:
        raise RuntimeError("Official source does not reach V2 transition window")
    declarations = {k: _dedupe_updates(v) for k, v in declarations.items()}
    guard = EventGuard(events, declarations)
    brands = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8")).get("stations") or {}
    bouclier = shield_phase_v2.with_cap_phases(bouclier_detector.metadata(max(years)))

    stations: dict[tuple[str, str], set[str]] = defaultdict(set)
    for sid, region, fuel in declarations:
        stations[(sid, region)].add(fuel)
    pointers: dict = {}
    sums = defaultdict(float); counts = defaultdict(int); reasons = Counter(); r2 = Counter()
    days = [d.date() for d in pd.date_range(start, end, freq="D")]
    phase_cache = {}
    def phase(fuel: str, day: date):
        key=(fuel,day)
        if key not in phase_cache: phase_cache[key]=shield_phase_v2.phase_for_day(bouclier,fuel,day)
        return phase_cache[key]

    for (sid, region), fuels in stations.items():
        region_kind = "corsica" if region == "corse" else "mainland"
        is_total = classify_registry_entry(brands.get(sid)) == TOTAL if region_kind == "corsica" else False
        relevant = set(fuels) | set(TARGET_FUELS)
        for day in days:
            state = {}
            for fuel in relevant:
                updates = declarations.get((sid, region, fuel), [])
                state[fuel] = _value_at(updates, pointers, (sid, region, fuel), day) if updates else (None, None)
            activity = {fuel: ts for fuel, (ts, _value) in state.items() if ts is not None}
            gazole_ts, gazole_price = state.get("Gazole", (None, None)); sp95_ts, sp95_price = state.get("SP95", (None, None))
            gp=phase("Gazole",day); sp=phase("SP95",day); gazole_cap=gp.cap if gp else None; sp95_cap=sp.cap if sp else None
            for fuel in TARGET_FUELS:
                last_ts, last_price = state.get(fuel, (None, None)); target_phase=phase(fuel,day)
                r2_verdict=None; age=reliability_policy_v2.age_days(last_ts,day)
                if region_kind == "corsica" and age is not None and age >= reliability_policy_v2.NORMAL_MAX_AGE_DAYS and at_cap(gazole_price,gazole_cap) and at_cap(sp95_price,sp95_cap):
                    r2["calls"] += 1
                    try:
                        r2_verdict=r2_guard_v2.stale_price_admissible(last_ts,day,bouclier_metadata=bouclier)
                        r2["true" if r2_verdict else "false"] += 1
                    except Exception as exc:
                        r2["unavailable"] += 1; r2[f"error:{type(exc).__name__}"] += 1; r2_verdict=None
                decision=reliability_policy_v2.evaluate(day=day,region_kind=region_kind,target_fuel=fuel,last_declared_at=last_ts,last_price=last_price,latest_price_valid=last_price is not None,target_rupture_active=guard.rupture_active(sid,fuel,day),independently_inactive=guard.closed(sid,day),is_total=is_total,shield_effective=target_phase is not None,applicable_cap=target_phase.cap if target_phase else None,phase_started_on=target_phase.started_on if target_phase else None,activity_by_fuel=activity,gazole_price=gazole_price,gazole_cap=gazole_cap,sp95_price=sp95_price,sp95_cap=sp95_cap,rotterdam_stale_price_admissible=r2_verdict)
                reasons[f"{region_kind}/{fuel}/{decision.reason}"] += 1
                if decision.eligible:
                    sums[(fuel, region, day)] += float(last_price); counts[(fuel, region, day)] += 1

    rows=[]
    for fuel in TARGET_FUELS:
        for day in days:
            means={}
            for region in ["corse"] + core.REGIONS:
                key=(fuel,region,day)
                if counts[key]: means[region]=sums[key]/counts[key]
            mainland=[means[r] for r in core.REGIONS if r in means]
            if mainland: means["moy_regions"] = sum(mainland)/len(mainland)
            for region,ttc in means.items():
                vat=1.13 if region=="corse" else 1.20
                rows.append((fuel,region,pd.Timestamp(day),ttc,ttc/vat))
    df=pd.DataFrame(rows,columns=["fuel","region","date","ttc","ht"])
    audit={"source_max_date":source_max.isoformat(),"evaluated_start":start.isoformat(),"evaluated_end":end.isoformat(),"reason_counts":dict(reasons),"r2":dict(r2),"events":dict(guard.stats),"bouclier":bouclier}
    return df,audit


def _r3(values): return round(sum(values)/len(values)+1e-12,3) if values else None

def _monday_offset(off: int) -> int:
    d=core.ORIGIN+timedelta(days=off); monday=d-timedelta(days=d.weekday()); return (monday-core.ORIGIN).days

def _month_key(off: int) -> str:
    d=core.ORIGIN+timedelta(days=off); return f"{d.year:04d}-{d.month:02d}"

def _weekly(points, first_week: int):
    buckets=defaultdict(lambda:[[],[]])
    for off,ttc,ht in points:
        wk=_monday_offset(off)
        if wk < first_week: continue
        if ttc is not None: buckets[wk][0].append(ttc)
        if ht is not None: buckets[wk][1].append(ht)
    return [[wk,_r3(v[0]),_r3(v[1])] for wk,v in sorted(buckets.items())]

def _monthly(points, first_month: str):
    buckets=defaultdict(lambda:[[],[]])
    for off,ttc,ht in points:
        mk=_month_key(off)
        if mk < first_month: continue
        if ttc is not None: buckets[mk][0].append(ttc)
        if ht is not None: buckets[mk][1].append(ht)
    return [[mk,_r3(v[0]),_r3(v[1])] for mk,v in sorted(buckets.items())]


def _generated_points(df: pd.DataFrame, fuel: str, region: str) -> list[list]:
    x=df[(df.fuel==fuel)&(df.region==region)].sort_values("date")
    return [[(r.date.date()-core.ORIGIN).days,round(float(r.ttc)+1e-12,3),round(float(r.ht)+1e-12,3)] for r in x.itertuples(index=False)]


def _merge_daily(old: list[list], generated: list[list], *, initial: bool) -> tuple[list[list],dict]:
    by_off={p[0]:p for p in generated}; switch_off=(SWITCH_DAY-core.ORIGIN).days; old_last=old[-1][0]; out=[]; rewrites=adds=0; deltas=[]
    for p in old:
        if initial and p[0] >= switch_off:
            q=by_off.get(p[0])
            if q is None: raise RuntimeError(f"Missing V2 daily replacement for {core.ORIGIN+timedelta(days=p[0])}")
            out.append(q); rewrites += int(q != p)
            if q != p and p[2] is not None and q[2] is not None: deltas.append(round((q[2]-p[2])*100,3))
        else: out.append(deepcopy(p))
    for off,q in sorted(by_off.items()):
        if off > old_last: out.append(q); adds += 1
    if not initial and out[:len(old)] != old: raise RuntimeError("Recurring C1 V2 build changed published daily history")
    return out,{"rewritten_rows":rewrites,"added_rows":adds,"max_abs_ht_delta_c_l":max((abs(x) for x in deltas),default=0.0),"mean_signed_ht_delta_c_l":round(sum(deltas)/len(deltas),4) if deltas else 0.0}


def main() -> None:
    args=parse_args(); baseline=json.loads((ROOT/args.input).read_text(encoding="utf-8")); target=date.fromisoformat(args.end) if args.end else date.today()-timedelta(days=1); years=[target.year-1,target.year]
    df,audit=build_v2_daily(years,SWITCH_DAY,target); target=date.fromisoformat(audit["evaluated_end"]); initial=not bool(((baseline.get("meta") or {}).get("v2") or {}).get("active")); candidate=deepcopy(baseline); series={}
    first_new_offsets=[]
    for fuel,short in core.FUELS.items():
        for region in ["corse","moy_regions"]+core.REGIONS:
            generated=_generated_points(df,fuel,region); old=baseline[short][region]["d"]; merged,stats=_merge_daily(old,generated,initial=initial); candidate[short][region]["d"]=merged; series[f"{short}/{region}/d"]=stats
            old_last=old[-1][0]
            if merged[-1][0] > old_last: first_new_offsets.append(old_last+1)
            if initial:
                first_week=(WEEKLY_SWITCH-core.ORIGIN).days; old_w=[p for p in baseline[short][region]["w"] if p[0] < first_week]; candidate[short][region]["w"]=old_w+_weekly(merged,first_week)
                old_m=[p for p in baseline[short][region]["m"] if p[0] < MONTHLY_SWITCH]; candidate[short][region]["m"]=old_m+_monthly(merged,MONTHLY_SWITCH)
            elif merged[-1][0] > old_last:
                first_new=old_last+1; first_week=_monday_offset(first_new); first_month=_month_key(first_new); candidate[short][region]["w"]=[p for p in baseline[short][region]["w"] if p[0] < first_week]+_weekly(merged,first_week); candidate[short][region]["m"]=[p for p in baseline[short][region]["m"] if p[0] < first_month]+_monthly(merged,first_month)

    meta=c1_bouclier_meta.attach_detector_bouclier(baseline.get("meta") or {},audit.get("bouclier")); meta=c1_last_date.attach_last_date(meta,candidate); meta["v2"]={"active":True,"version":"A4C-C1-V2-2026-07-23","daily_switch_date":SWITCH_DAY.isoformat(),"weekly_switch_date":WEEKLY_SWITCH.isoformat(),"monthly_switch":"2026-08","history_before_switch_preserved":True,"controlled_transition_applied":initial or bool((meta.get("v2") or {}).get("controlled_transition_applied")),"event_reopening_rule":"open rupture -> later same-fuel declaration; open closure -> later any-fuel station declaration; explicit end wins"}; candidate["meta"]=meta
    output=ROOT/args.output; summary_path=ROOT/args.summary; output.parent.mkdir(parents=True,exist_ok=True); summary_path.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(candidate,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    switch_off=(SWITCH_DAY-core.ORIGIN).days; protected=0
    for fuel,short in core.FUELS.items():
        for region in ["corse","moy_regions"]+core.REGIONS:
            old=baseline[short][region]["d"]; new=candidate[short][region]["d"]; old_prefix=[p for p in old if p[0] < switch_off]; new_prefix=[p for p in new if p[0] < switch_off]
            if old_prefix != new_prefix: raise RuntimeError(f"Pre-transition C1 history changed: {short}/{region}")
            protected += len(old_prefix)
    summary={"status":"c1-v2-production-candidate","production_modified":False,"initial_transition":initial,"daily_switch_date":SWITCH_DAY.isoformat(),"weekly_switch_date":WEEKLY_SWITCH.isoformat(),"monthly_switch":MONTHLY_SWITCH,"target_end":target.isoformat(),"protected_daily_rows_verified":protected,"rewritten_daily_rows_total":sum(v["rewritten_rows"] for v in series.values()),"added_daily_rows_total":sum(v["added_rows"] for v in series.values()),"series":series,"engine":audit}
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
