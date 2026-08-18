#!/usr/bin/env python3
"""Generate current-year regional daily fuel prices from the official annual XML stock.

This module is the shared numerical core used by the weekly append-only updater and by the
TotalEnergies ceiling detector.

Method for carburantscorse1:
- Gazole + SP95;
- motorway stations (pop=A) excluded;
- last declaration of a station/fuel/day wins;
- forward-fill limited to 45 days, as in the published dashboard methodology;
- suspicious prices < 1.10 €/L or > 3.00 €/L are flagged by state and excluded from means
  until the station publishes a subsequent valid value; they are never silently corrected;
- station means are computed by region; "moy_regions" is the equal-weight mean of the 12
  mainland regional means;
- Corse HT uses 13% VAT, mainland HT 20%.

The 1.10–3.00 reliability band and the no-auto-correction principle come from the recovered
A4C methodological project saved on 14 June 2026. The 45-day fill remains specific to this
published Corse-vs-regions dashboard; the separate Corse-vs-BdR project used longer,
territory-specific reliability thresholds and is not silently substituted here.
"""
from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
import xml.etree.ElementTree as ET

import pandas as pd

ORIGIN = date(2022, 1, 1)
FUELS = {"Gazole": "G", "SP95": "S"}
MAX_FFILL_DAYS = 45
PRICE_MIN = 1.10
PRICE_MAX = 3.00

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
    req = urllib.request.Request(url, headers={"User-Agent":"A4C-observatoire/1.2"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def is_reliable_price(value: float | None) -> bool:
    return value is not None and PRICE_MIN <= value <= PRICE_MAX


def parse_year(year: int):
    """Map (station, region, fuel) -> chronological updates.

    An aberrant numeric declaration is retained as an update whose value is ``None``. This is
    important: the bad declaration must stop the previous price from being carried forward,
    rather than being ignored as though it never occurred. A later valid declaration resumes
    the station's contribution to averages.
    """
    raw = download(year)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
    if not name:
        raise RuntimeError("Official ZIP contains no XML")

    out = defaultdict(list)
    price_rows = valid_rows = aberrant_rows = 0
    min_ts = max_ts = None
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
                fuel = p.attrib.get("nom")
                if fuel not in FUELS:
                    continue
                price_rows += 1
                try:
                    ts = datetime.fromisoformat(p.attrib["maj"])
                    raw_value = float(p.attrib["valeur"])
                except (KeyError, ValueError):
                    continue
                value = raw_value if is_reliable_price(raw_value) else None
                if value is None:
                    aberrant_rows += 1
                else:
                    valid_rows += 1
                out[(sid, region, fuel)].append((ts, value))
                min_ts = ts if min_ts is None or ts < min_ts else min_ts
                max_ts = ts if max_ts is None or ts > max_ts else max_ts
            elem.clear()

    print(
        f"{year}: {price_rows:,} Gazole/SP95 rows; valid={valid_rows:,}; "
        f"aberrant={aberrant_rows:,}; dates {min_ts} -> {max_ts}",
        file=sys.stderr,
    )
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

    for (_sid, region, fuel), vals in changes.items():
        vals.sort(key=lambda x: x[0])
        # Last declaration of the calendar day wins, including an aberrant declaration.
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
            if last_ts is None:
                continue
            if (d - last_ts.date()).days > MAX_FFILL_DAYS:
                continue
            if last_value is None:
                # An explicitly suspect price was the latest declaration: exclude this station
                # until it publishes a subsequent valid value.
                continue
            k = (fuel, region, d)
            sums[k] += last_value
            counts[k] += 1

    rows = []
    for fuel in FUELS:
        for stamp in days:
            d = stamp.date()
            means = {}
            for region in ["corse"] + REGIONS:
                k = (fuel, region, d)
                if counts[k]:
                    means[region] = sums[k] / counts[k]
            mainland = [means[r] for r in REGIONS if r in means]
            if mainland:
                means["moy_regions"] = sum(mainland) / len(mainland)
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
