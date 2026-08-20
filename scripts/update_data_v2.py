#!/usr/bin/env python3
"""Generate current-year regional daily fuel prices from the official annual XML stock.

This module is the shared numerical core used by the weekly append-only updater and by the
TotalEnergies ceiling detector.

Method for carburantscorse1:
- Gazole + SP95;
- motorway stations (pop=A) excluded;
- last declaration of a station/fuel/day wins;
- station activity is considered fresh for 45 days after any Gazole/SP95 declaration;
- while the station remains active, the last valid price of each fuel is carried forward even
  when that fuel itself has not changed for more than 45 days;
- an active rupture for a fuel suppresses that fuel until the rupture ends;
- suspicious prices < 1.10 €/L or > 3.00 €/L are flagged by state and excluded from means
  until the station publishes a subsequent valid value; they are never silently corrected;
- station means are computed by region; "moy_regions" is the equal-weight mean of the 12
  mainland regional means;
- Corse HT uses 13% VAT, mainland HT 20%.

The 1.10–3.00 reliability band and the no-auto-correction principle come from the recovered
A4C methodological project saved on 14 June 2026. The 45-day threshold is now a station-
activity threshold, not a per-fuel price-age threshold.
"""
from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

ORIGIN = date(2022, 1, 1)
FUELS = {"Gazole": "G", "SP95": "S"}
MAX_STATION_INACTIVE_DAYS = 45
MAX_FFILL_DAYS = MAX_STATION_INACTIVE_DAYS
PRICE_MIN = 1.10
PRICE_MAX = 3.00
CACHE_DIR = Path(".cache/official-fuel")

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
    """Download one annual official ZIP once per workflow process tree."""
    cache_file = CACHE_DIR / f"PrixCarburants_annuel_{year}.zip"
    if cache_file.exists():
        raw = cache_file.read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                if not any(n.lower().endswith(".xml") for n in zf.namelist()):
                    raise zipfile.BadZipFile("cached ZIP contains no XML")
            print(f"Using workflow cache {cache_file} ({len(raw):,} bytes)", file=sys.stderr)
            return raw
        except zipfile.BadZipFile:
            print(f"Discarding invalid workflow cache {cache_file}", file=sys.stderr)
            cache_file.unlink(missing_ok=True)

    url = annual_url(year)
    print(f"Downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent":"A4C-observatoire/1.4"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        if not any(n.lower().endswith(".xml") for n in zf.namelist()):
            raise RuntimeError("Official ZIP contains no XML")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(cache_file)
    print(f"Cached for this workflow: {cache_file} ({len(raw):,} bytes)", file=sys.stderr)
    return raw


def is_reliable_price(value: float | None) -> bool:
    return value is not None and PRICE_MIN <= value <= PRICE_MAX


def parse_year_state(year: int):
    """Return official prices, station-activity events and fuel ruptures for one year."""
    raw = download(year)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
    if not name:
        raise RuntimeError("Official ZIP contains no XML")

    prices = defaultdict(list)
    activity = defaultdict(list)
    ruptures = defaultdict(list)
    price_rows = valid_rows = aberrant_rows = rupture_rows = 0
    min_ts = max_ts = None

    with zf.open(name) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag.rsplit("}", 1)[-1] != "pdv":
                continue
            if elem.attrib.get("pop") == "A":
                elem.clear()
                continue
            region = region_from_cp(elem.attrib.get("cp", ""))
            if not region:
                elem.clear()
                continue
            sid = elem.attrib.get("id", "")

            for child in list(elem):
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "prix":
                    fuel = child.attrib.get("nom")
                    if fuel not in FUELS:
                        continue
                    price_rows += 1
                    try:
                        ts = datetime.fromisoformat(child.attrib["maj"])
                    except (KeyError, ValueError):
                        continue
                    activity[(sid, region)].append(ts)
                    try:
                        raw_value = float(child.attrib["valeur"])
                    except (KeyError, ValueError):
                        value = None
                    else:
                        value = raw_value if is_reliable_price(raw_value) else None
                    if value is None:
                        aberrant_rows += 1
                    else:
                        valid_rows += 1
                    prices[(sid, region, fuel)].append((ts, value))
                    min_ts = ts if min_ts is None or ts < min_ts else min_ts
                    max_ts = ts if max_ts is None or ts > max_ts else max_ts

                elif tag == "rupture":
                    fuel = child.attrib.get("nom")
                    if fuel not in FUELS:
                        continue
                    try:
                        start_ts = datetime.fromisoformat(child.attrib["debut"])
                    except (KeyError, ValueError):
                        continue
                    end_raw = child.attrib.get("fin")
                    try:
                        end_ts = datetime.fromisoformat(end_raw) if end_raw else None
                    except ValueError:
                        end_ts = None
                    ruptures[(sid, region, fuel)].append((start_ts, end_ts))
                    activity[(sid, region)].append(start_ts)
                    if end_ts is not None:
                        activity[(sid, region)].append(end_ts)
                    rupture_rows += 1

            elem.clear()

    print(
        f"{year}: {price_rows:,} Gazole/SP95 rows; valid={valid_rows:,}; "
        f"aberrant={aberrant_rows:,}; ruptures={rupture_rows:,}; dates {min_ts} -> {max_ts}",
        file=sys.stderr,
    )
    return prices, activity, ruptures


def parse_year(year: int):
    """Backward-compatible price-only view used by older scripts."""
    prices, _activity, _ruptures = parse_year_state(year)
    return prices


def load_market_state(year: int):
    """Combine N-1 and N official state needed to evaluate one publication year."""
    prices = defaultdict(list)
    activity = defaultdict(list)
    ruptures = defaultdict(list)
    for y in (year - 1, year):
        yp, ya, yr = parse_year_state(y)
        for key, vals in yp.items():
            prices[key].extend(vals)
        for key, vals in ya.items():
            activity[key].extend(vals)
        for key, vals in yr.items():
            ruptures[key].extend(vals)
    for mapping in (prices, activity, ruptures):
        for vals in mapping.values():
            vals.sort(key=lambda x: x[0] if isinstance(x, tuple) else x)
    return prices, activity, ruptures


def station_active(last_activity_ts: datetime | None, day: date) -> bool:
    return (
        last_activity_ts is not None
        and 0 <= (day - last_activity_ts.date()).days <= MAX_STATION_INACTIVE_DAYS
    )


def rupture_active(intervals, day: date) -> bool:
    """Whether a rupture is still open at the end of a calendar day."""
    end_of_day = datetime.combine(day, time.max)
    return any(start <= end_of_day and (end is None or end > end_of_day) for start, end in intervals)


def fuel_value_eligible(
    last_price_ts: datetime | None,
    last_value: float | None,
    last_activity_ts: datetime | None,
    intervals,
    day: date,
) -> bool:
    """Return whether a station-fuel value contributes to the daily average.

    Deliberately, the age of ``last_price_ts`` is not capped: an unchanged price remains valid
    while the station is active. Station inactivity, an invalid latest price, or an active
    rupture excludes the value.
    """
    if last_price_ts is None or last_value is None:
        return False
    if not station_active(last_activity_ts, day):
        return False
    if rupture_active(intervals, day):
        return False
    return True


def build_daily(year: int) -> pd.DataFrame:
    prices, activity, ruptures = load_market_state(year)

    start = date(year, 1, 1)
    end = min(date.today() - timedelta(days=1), date(year, 12, 31))
    days = pd.date_range(start, end, freq="D")
    sums = defaultdict(float)
    counts = defaultdict(int)

    for (sid, region, fuel), vals in prices.items():
        vals.sort(key=lambda x: x[0])

        per_day = {}
        for ts, value in vals:
            per_day[ts.date()] = (ts, value)
        updates = sorted(per_day.values(), key=lambda x: x[0])
        if not updates:
            continue

        activity_updates = sorted(activity.get((sid, region), []))
        fuel_ruptures = ruptures.get((sid, region, fuel), [])

        j = 0
        last_ts = None
        last_value = None
        while j < len(updates) and updates[j][0].date() < start:
            last_ts, last_value = updates[j]
            j += 1

        a = 0
        last_activity_ts = None
        while a < len(activity_updates) and activity_updates[a].date() < start:
            last_activity_ts = activity_updates[a]
            a += 1

        for stamp in days:
            d = stamp.date()
            while j < len(updates) and updates[j][0].date() <= d:
                last_ts, last_value = updates[j]
                j += 1
            while a < len(activity_updates) and activity_updates[a].date() <= d:
                last_activity_ts = activity_updates[a]
                a += 1

            if not fuel_value_eligible(
                last_ts, last_value, last_activity_ts, fuel_ruptures, d
            ):
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
