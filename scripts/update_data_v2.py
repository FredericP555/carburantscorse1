#!/usr/bin/env python3
"""Rebuild only the current-year portion of data.json from official annual XML stocks.

Safety: nothing is written unless the overlap already present in data.json validates.
Historical years before the selected year are preserved unchanged.
"""
from __future__ import annotations

import argparse
import io
import json
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
    "Auvergne-Rhône-Alpes","Bourgogne-Franche-Comté","Bretagne",
    "Centre-Val de Loire","Grand Est","Hauts-de-France","Île-de-France",
    "Normandie","Nouvelle-Aquitaine","Occitanie","PACA","Pays de la Loire",
]
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


def annual_url(year: int) -> str:
    if year == date.today().year:
        return "https://donnees.roulez-eco.fr/opendata/annee"
    return f"https://donnees.roulez-eco.fr/opendata/annee/{year}"


def download(year: int) -> bytes:
    url = annual_url(year)
    print(f"Downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent":"A4C-observatoire/1.1"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def parse_year(year: int):
    """Map (station, region, fuel) -> chronological price updates."""
    raw = download(year)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
    if not name:
        raise RuntimeError("Official ZIP contains no XML")

    out = defaultdict(list)
    price_rows = 0
    accepted = 0
    min_ts = None
    max_ts = None
    with zf.open(name) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag.rsplit("}", 1)[-1] != "pdv":
                continue
            if elem.attrib.get("pop") == "A":
                elem.clear(); continue
            region = region_from_cp(elem.attrib.get("cp", ""))
            if not region:
                elem.clear(); continue
            sid = elem.attrib.get("id", "")
            for p in list(elem):
                if p.tag.rsplit("}", 1)[-1] != "prix":
                    continue
                price_rows += 1
                fuel = p.attrib.get("nom")
                if fuel not in FUELS:
                    continue
                try:
                    # Official files now use ISO 8601 with a T separator.
                    ts = datetime.fromisoformat(p.attrib["maj"])
                    value = float(p.attrib["valeur"])
                except (KeyError, ValueError):
                    continue
                if not (0.5 <= value <= 4.0):
                    continue
                out[(sid, region, fuel)].append((ts, value))
                accepted += 1
                min_ts = ts if min_ts is None or ts < min_ts else min_ts
                max_ts = ts if max_ts is None or ts > max_ts else max_ts
            elem.clear()
    print(f"{year}: accepted {accepted:,} Gazole/SP95 rows; dates {min_ts} -> {max_ts}", file=sys.stderr)
    return out


def build_daily(year: int) -> pd.DataFrame:
    changes = defaultdict(list)
    for y in (year - 1, year):
        for key, vals in parse_year(y).items():
            changes[key].extend(vals)

    start = date(year, 1, 1)
    end = min(date.today() - timedelta(days=1), date(year, 12, 31))
    days = pd.date_range(start, end, freq="D")
    sums = defaultdict(float)
    counts = defaultdict(int)

    for (sid, region, fuel), vals in changes.items():
        vals.sort(key=lambda x: x[0])
        # Last declared price of each calendar day wins.
        per_day = {}
        for ts, value in vals:
            per_day[ts.date()] = (ts, value)
        updates = sorted(per_day.values(), key=lambda x: x[0])
        if not updates:
            continue

        j = 0
        last_ts = None
        last_value = None
        while j < len(updates) and updates[j][0].date() < start:
            last_ts, last_value = updates[j]
            j += 1

        for stamp in days:
            d = stamp.date()
            while j < len(updates) and updates[j][0].date() <= d:
                last_ts, last_value = updates[j]
                j += 1
            if last_ts is None or last_value is None:
                continue
            if (d - last_ts.date()).days > MAX_FFILL_DAYS:
                continue
            k = (fuel, region, d)
            sums[k] += last_value
            counts[k] += 1

    rows = []
    mainland_regions = REGIONS
    for fuel in FUELS:
        for stamp in days:
            d = stamp.date()
            means = {}
            for region in ["corse"] + mainland_regions:
                k = (fuel, region, d)
                if counts[k]:
                    means[region] = sums[k] / counts[k]
            vals = [means[r] for r in mainland_regions if r in means]
            if vals:
                means["moy_regions"] = sum(vals) / len(vals)
            for region, ttc in means.items():
                vat = 1.13 if region == "corse" else 1.20
                rows.append((fuel, region, pd.Timestamp(d), ttc, ttc / vat))

    df = pd.DataFrame(rows, columns=["fuel","region","date","ttc","ht"])
    print(f"Built {len(df):,} regional daily rows", file=sys.stderr)
    return df


def r3(v):
    return None if pd.isna(v) else round(float(v) + 1e-12, 3)


def offset(ts) -> int:
    return (ts.date() - ORIGIN).days


def make_series(df: pd.DataFrame, region: str, mode: str):
    x = df[df.region == region].set_index("date")[["ttc","ht"]].sort_index()
    if x.empty:
        return []
    if mode == "d":
        return [[offset(i), r3(r.ttc), r3(r.ht)] for i, r in x.iterrows()]
    if mode == "w":
        t = x.copy()
        t["week"] = [i - pd.Timedelta(days=i.weekday()) for i in t.index]
        g = t.groupby("week")[["ttc","ht"]].mean()
        return [[offset(i), r3(r.ttc), r3(r.ht)] for i, r in g.iterrows()]
    if mode == "m":
        g = x.groupby(x.index.to_period("M"))[["ttc","ht"]].mean()
        return [[str(i), r3(r.ttc), r3(r.ht)] for i, r in g.iterrows()]
    raise ValueError(mode)


def payload(df: pd.DataFrame):
    out = {"origin":str(ORIGIN), "G":{}, "S":{}}
    names = ["corse","moy_regions"] + REGIONS
    for fuel, short in FUELS.items():
        f = df[df.fuel == fuel]
        for region in names:
            out[short][region] = {
                "m":make_series(f, region, "m"),
                "w":make_series(f, region, "w"),
                "d":make_series(f, region, "d"),
            }
    return out


def validate(old: dict, new: dict, year: int, tolerance: float) -> bool:
    cut = (date(year,1,1) - ORIGIN).days
    failures = []
    print("Validation against existing current-year daily TTC:", file=sys.stderr)
    for fuel in ("G","S"):
        for region in ["corse","moy_regions"] + REGIONS:
            om = {p[0]:p[1] for p in old[fuel][region]["d"] if p[0] >= cut}
            nm = {p[0]:p[1] for p in new[fuel][region]["d"] if p[0] in om}
            diffs = [abs(nm[k]-om[k]) for k in nm if nm[k] is not None and om[k] is not None]
            if not diffs:
                failures.append(f"{fuel}/{region}: no overlap")
                continue
            mae = sum(diffs)/len(diffs)
            mx = max(diffs)
            print(f"  {fuel} {region:28} n={len(diffs):3d} MAE={mae:.4f} max={mx:.4f}", file=sys.stderr)
            if mx > tolerance:
                failures.append(f"{fuel}/{region}: max Δ={mx:.3f} €/L > {tolerance:.3f}")
    if failures:
        print("VALIDATION FAILED", file=sys.stderr)
        for f in failures:
            print(" - "+f, file=sys.stderr)
        return False
    print("VALIDATION OK", file=sys.stderr)
    return True


def merge(old: dict, new: dict, year: int):
    out = json.loads(json.dumps(old))
    dcut = (date(year,1,1)-ORIGIN).days
    jan1 = date(year,1,1)
    wcut = ((jan1-timedelta(days=jan1.weekday()))-ORIGIN).days
    mcut = f"{year:04d}-01"
    for fuel in ("G","S"):
        for region, series in new[fuel].items():
            out[fuel][region]["d"] = [p for p in out[fuel][region]["d"] if p[0] < dcut] + series["d"]
            out[fuel][region]["w"] = [p for p in out[fuel][region]["w"] if p[0] < wcut] + series["w"]
            out[fuel][region]["m"] = [p for p in out[fuel][region]["m"] if p[0] < mcut] + series["m"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data.json")
    ap.add_argument("--output", default="data-new.json")
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--tolerance", type=float, default=0.010)
    args = ap.parse_args()
    old = json.loads(Path(args.input).read_text(encoding="utf-8"))
    new = payload(build_daily(args.year))
    if not validate(old, new, args.year, args.tolerance):
        return 2
    merged = merge(old, new, args.year)
    Path(args.output).write_text(json.dumps(merged, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
