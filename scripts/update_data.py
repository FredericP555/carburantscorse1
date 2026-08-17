#!/usr/bin/env python3
"""Regenerate the current-year part of data.json from the official fuel-price Open Data.

Safety principle:
- historical data before the current year is kept byte-for-byte logically unchanged;
- the current year is rebuilt from official XML stocks;
- before writing, the rebuilt series are compared with the overlap already present in data.json;
- validation failure stops the run, so the dashboard cannot silently drift.

The script intentionally does NOT yet automate the editorial text or the TotalEnergies
'bouclier effectif' zones. Those will be added only after the data pipeline is validated.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

ORIGIN = date(2022, 1, 1)
FUELS = {"Gazole": "G", "SP95": "S"}
MAX_FFILL_DAYS = 45

REGIONS = [
    "Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne",
    "Centre-Val de Loire", "Grand Est", "Hauts-de-France", "Île-de-France",
    "Normandie", "Nouvelle-Aquitaine", "Occitanie", "PACA", "Pays de la Loire",
]

# Department -> dashboard region. Overseas departments are deliberately absent.
DEP_REGION = {
    "01":"Auvergne-Rhône-Alpes","03":"Auvergne-Rhône-Alpes","07":"Auvergne-Rhône-Alpes","15":"Auvergne-Rhône-Alpes","26":"Auvergne-Rhône-Alpes","38":"Auvergne-Rhône-Alpes","42":"Auvergne-Rhône-Alpes","43":"Auvergne-Rhône-Alpes","63":"Auvergne-Rhône-Alpes","69":"Auvergne-Rhône-Alpes","73":"Auvergne-Rhône-Alpes","74":"Auvergne-Rhône-Alpes",
    "21":"Bourgogne-Franche-Comté","25":"Bourgogne-Franche-Comté","39":"Bourgogne-Franche-Comté","58":"Bourgogne-Franche-Comté","70":"Bourgogne-Franche-Comté","71":"Bourgogne-Franche-Comté","89":"Bourgogne-Franche-Comté","90":"Bourgogne-Franche-Comté",
    "22":"Bretagne","29":"Bretagne","35":"Bretagne","56":"Bretagne",
    "18":"Centre-Val de Loire","28":"Centre-Val de Loire","36":"Centre-Val de Loire","37":"Centre-Val de Loire","41":"Centre-Val de Loire","45":"Centre-Val de Loire",
    "08":"Grand Est","10":"Grand Est","51":"Grand Est","52":"Grand Est","54":"Grand Est","55":"Grand Est","57":"Grand Est","67":"Grand Est","68":"Grand Est","88":"Grand Est",
    "02":"Hauts-de-France","59":"Hauts-de-France","60":"Hauts-de-France","62":"Hauts-de-France","80":"Hauts-de-France",
    "75":"Île-de-France","77":"Île-de-France","78":"Île-de-France","91":"Île-de-France","92":"Île-de-France","93":"Île-de-France","94":"Île-de-France","95":"Île-de-France",
    "14":"Normandie","27":"Normandie","50":"Normandie","61":"Normandie","76":"Normandie",
    "16":"Nouvelle-Aquitaine","17":"Nouvelle-Aquitaine","19":"Nouvelle-Aquitaine","23":"Nouvelle-Aquitaine","24":"Nouvelle-Aquitaine","33":"Nouvelle-Aquitaine","40":"Nouvelle-Aquitaine","47":"Nouvelle-Aquitaine","64":"Nouvelle-Aquitaine","79":"Nouvelle-Aquitaine","86":"Nouvelle-Aquitaine","87":"Nouvelle-Aquitaine",
    "09":"Occitanie","11":"Occitanie","12":"Occitanie","30":"Occitanie","31":"Occitanie","32":"Occitanie","34":"Occitanie","46":"Occitanie","48":"Occitanie","65":"Occitanie","66":"Occitanie","81":"Occitanie","82":"Occitanie",
    "04":"PACA","05":"PACA","06":"PACA","13":"PACA","83":"PACA","84":"PACA",
    "44":"Pays de la Loire","49":"Pays de la Loire","53":"Pays de la Loire","72":"Pays de la Loire","85":"Pays de la Loire",
}


def region_from_cp(cp: str) -> str | None:
    cp = (cp or "").strip().zfill(5)
    if cp.startswith("20"):
        return "corse"
    return DEP_REGION.get(cp[:2])


def download_zip(year: int) -> bytes:
    current_year = date.today().year
    url = "https://donnees.roulez-eco.fr/opendata/annee" if year == current_year else f"https://donnees.roulez-eco.fr/opendata/annee/{year}"
    print(f"Downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "A4C-observatoire/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def xml_stream(zip_bytes: bytes):
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
    if not xml_names:
        raise RuntimeError("No XML file found in official ZIP")
    return zf.open(xml_names[0])


def parse_year(year: int):
    """Return station/fuel price changes for one annual stock.

    Key = (station_id, region, fuel), value = list[(timestamp, price)].
    Autoroute stations (pop=A) are excluded, matching the current dashboard method.
    """
    out = defaultdict(list)
    with xml_stream(download_zip(year)) as fh:
        for event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "pdv":
                continue
            if elem.attrib.get("pop") == "A":
                elem.clear(); continue
            station_id = elem.attrib.get("id", "")
            region = region_from_cp(elem.attrib.get("cp", ""))
            if not region:
                elem.clear(); continue
            for p in elem.findall("prix"):
                fuel = p.attrib.get("nom")
                if fuel not in FUELS:
                    continue
                try:
                    ts = datetime.strptime(p.attrib["maj"], "%Y-%m-%d %H:%M:%S")
                    value = float(p.attrib["valeur"])
                except (KeyError, ValueError):
                    continue
                # Conservative plausibility guard. It catches corrupt records without
                # imposing a narrow market-price assumption.
                if not (0.5 <= value <= 4.0):
                    continue
                out[(station_id, region, fuel)].append((ts, value))
            elem.clear()
    return out


def build_daily(current_year: int):
    """Build station-forward-filled daily regional means for current_year.

    Previous-year records are included solely to seed 1 January. A station price is
    carried for at most 45 days, exactly as documented by the existing dashboard.
    """
    changes = defaultdict(list)
    for y in (current_year - 1, current_year):
        for key, vals in parse_year(y).items():
            changes[key].extend(vals)

    start = date(current_year, 1, 1)
    end = min(date.today() - timedelta(days=1), date(current_year, 12, 31))
    if end < start:
        raise RuntimeError("No completed day in current year")
    days = pd.date_range(start, end, freq="D")

    # sums/counts by (fuel, region, day), avoiding a huge station x day DataFrame.
    sums = defaultdict(float)
    counts = defaultdict(int)

    for (station_id, region, fuel), vals in changes.items():
        vals.sort(key=lambda x: x[0])
        # Keep last update per calendar day.
        daily_updates = {}
        for ts, value in vals:
            daily_updates[ts.date()] = (ts, value)
        sorted_updates = sorted(daily_updates.values(), key=lambda x: x[0])
        if not sorted_updates:
            continue

        j = 0
        last_ts = None
        last_value = None
        while j < len(sorted_updates) and sorted_updates[j][0].date() < start:
            last_ts, last_value = sorted_updates[j]
            j += 1

        for dts in days:
            d = dts.date()
            while j < len(sorted_updates) and sorted_updates[j][0].date() <= d:
                last_ts, last_value = sorted_updates[j]
                j += 1
            if last_ts is None or last_value is None:
                continue
            if (d - last_ts.date()).days > MAX_FFILL_DAYS:
                continue
            key = (fuel, region, d)
            sums[key] += last_value
            counts[key] += 1

    rows = []
    all_regions = ["corse"] + REGIONS
    for fuel in FUELS:
        for dts in days:
            d = dts.date()
            region_means = {}
            for region in all_regions:
                key = (fuel, region, d)
                if counts[key]:
                    region_means[region] = sums[key] / counts[key]
            # Mean of the 12 regional means: this preserves the current dashboard's
            # 'moyenne toutes régions' concept rather than weighting by station count.
            mainland = [region_means[r] for r in REGIONS if r in region_means]
            if mainland:
                region_means["moy_regions"] = sum(mainland) / len(mainland)
            for region, ttc in region_means.items():
                vat = 1.13 if region == "corse" else 1.20
                rows.append((fuel, region, pd.Timestamp(d), ttc, ttc / vat))

    return pd.DataFrame(rows, columns=["fuel", "region", "date", "ttc", "ht"])


def r3(v):
    if pd.isna(v):
        return None
    return round(float(v) + 1e-12, 3)


def day_offset(ts) -> int:
    return (ts.date() - ORIGIN).days


def make_resolution(df: pd.DataFrame, region: str, mode: str):
    x = df[df.region == region].set_index("date")[["ttc", "ht"]].sort_index()
    if x.empty:
        return []
    if mode == "d":
        return [[day_offset(idx), r3(row.ttc), r3(row.ht)] for idx, row in x.iterrows()]
    if mode == "w":
        # Monday-labelled weeks; partial first/last weeks are kept.
        tmp = x.copy()
        tmp["week"] = [idx - pd.Timedelta(days=idx.weekday()) for idx in tmp.index]
        g = tmp.groupby("week")[["ttc", "ht"]].mean()
        return [[day_offset(idx), r3(row.ttc), r3(row.ht)] for idx, row in g.iterrows()]
    if mode == "m":
        g = x.groupby(x.index.to_period("M"))[["ttc", "ht"]].mean()
        return [[str(idx), r3(row.ttc), r3(row.ht)] for idx, row in g.iterrows()]
    raise ValueError(mode)


def generated_payload(df: pd.DataFrame):
    result = {"origin": str(ORIGIN), "G": {}, "S": {}}
    series_names = ["corse", "moy_regions"] + REGIONS
    for fuel, short in FUELS.items():
        fdf = df[df.fuel == fuel]
        for region in series_names:
            result[short][region] = {
                "m": make_resolution(fdf, region, "m"),
                "w": make_resolution(fdf, region, "w"),
                "d": make_resolution(fdf, region, "d"),
            }
    return result


def merge_current_year(old: dict, new: dict, year: int):
    merged = json.loads(json.dumps(old))
    d_cut = (date(year, 1, 1) - ORIGIN).days
    # Week containing Jan 1 starts on the preceding Monday.
    jan1 = date(year, 1, 1)
    w_cut = ((jan1 - timedelta(days=jan1.weekday())) - ORIGIN).days
    m_cut = f"{year:04d}-01"
    for fuel in ("G", "S"):
        for region, series in new[fuel].items():
            if region not in merged[fuel]:
                merged[fuel][region] = {"m": [], "w": [], "d": []}
            merged[fuel][region]["d"] = [p for p in merged[fuel][region]["d"] if p[0] < d_cut] + series["d"]
            merged[fuel][region]["w"] = [p for p in merged[fuel][region]["w"] if p[0] < w_cut] + series["w"]
            merged[fuel][region]["m"] = [p for p in merged[fuel][region]["m"] if p[0] < m_cut] + series["m"]
    return merged


def validate_overlap(old: dict, new: dict, year: int, tolerance: float):
    """Compare current-year daily TTC against existing data.json overlap."""
    start_off = (date(year, 1, 1) - ORIGIN).days
    failures = []
    summary = []
    for fuel in ("G", "S"):
        for region in ["corse", "moy_regions"] + REGIONS:
            old_map = {p[0]: p[1] for p in old[fuel][region]["d"] if p[0] >= start_off}
            new_map = {p[0]: p[1] for p in new[fuel][region]["d"] if p[0] in old_map}
            diffs = [abs(new_map[k] - old_map[k]) for k in new_map if old_map[k] is not None and new_map[k] is not None]
            if not diffs:
                failures.append(f"{fuel}/{region}: no overlap")
                continue
            mae = sum(diffs) / len(diffs)
            maxdiff = max(diffs)
            summary.append((fuel, region, len(diffs), mae, maxdiff))
            if maxdiff > tolerance:
                failures.append(f"{fuel}/{region}: max Δ={maxdiff:.3f} €/L > {tolerance:.3f}")
    print("Validation against existing 2026 daily series:", file=sys.stderr)
    for fuel, region, n, mae, mx in summary:
        print(f"  {fuel:1} {region:28} n={n:3d} MAE={mae:.4f} max={mx:.4f}", file=sys.stderr)
    if failures:
        print("\nVALIDATION FAILED:", file=sys.stderr)
        for f in failures:
            print(" - " + f, file=sys.stderr)
        return False
    print("VALIDATION OK", file=sys.stderr)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data.json")
    ap.add_argument("--output", default="data.json")
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--tolerance", type=float, default=0.010, help="maximum allowed overlap difference in €/L")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    old = json.loads(Path(args.input).read_text(encoding="utf-8"))
    daily = build_daily(args.year)
    new = generated_payload(daily)

    if not args.no_validate and not validate_overlap(old, new, args.year, args.tolerance):
        return 2

    merged = merge_current_year(old, new, args.year)
    Path(args.output).write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
