#!/usr/bin/env python3
"""Build the authoritative Corsica station -> brand registry.

Station IDs and station metadata come from the official annual price XML. The brand is not
present in that open-data XML, but the official prix-carburants.gouv.fr station page exposes it
as ``Marque : ...``. We therefore join both official sources on the station ID.

The registry is append-preserving: stations seen in previous runs remain in the file, while
stations present in the current annual XML are refreshed from their official station page.
This avoids losing historical IDs when a station closes or changes identifier.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

import update_data_v2 as core

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "config" / "corse_station_brands.json"
STATION_URL = "https://www.prix-carburants.gouv.fr/station/{station_id}"
USER_AGENT = "A4C-observatoire-station-brands/1.0"


class TextTokens(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)


def extract_brand_from_html(raw: str) -> str | None:
    """Extract the official ``Marque`` value from one station details page."""
    parser = TextTokens()
    parser.feed(raw)
    tokens = [html.unescape(t).strip() for t in parser.tokens if t.strip()]
    for idx, token in enumerate(tokens):
        compact = re.sub(r"\s+", " ", token).strip()
        match = re.match(r"^Marque\s*:\s*(.*)$", compact, flags=re.I)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline:
            return inline
        for nxt in tokens[idx + 1 : idx + 5]:
            nxt = nxt.strip()
            if nxt:
                return nxt
    return None


def canonical_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    value = " ".join(raw.split()).strip()
    folded = value.casefold()
    if folded.startswith("totalenergies") or folded == "total":
        return "TotalEnergies"
    if folded.startswith("vito"):
        return "VITO"
    if folded == "eni" or folded.startswith("eni "):
        return "ENI"
    return value


def current_corsica_stations(year: int) -> dict[str, dict]:
    """Return current Corsica PDVs from the official annual XML, keyed by station ID."""
    raw = core.download(year)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not name:
            raise RuntimeError("Official ZIP contains no XML")
        stations: dict[str, dict] = {}
        with zf.open(name) as fh:
            for _event, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag.rsplit("}", 1)[-1] != "pdv":
                    continue
                cp = (elem.attrib.get("cp") or "").strip()
                if not cp.startswith("20"):
                    elem.clear()
                    continue
                sid = (elem.attrib.get("id") or "").strip()
                if not sid:
                    elem.clear()
                    continue
                address = ""
                city = ""
                for child in list(elem):
                    tag = child.tag.rsplit("}", 1)[-1]
                    if tag == "adresse":
                        address = (child.text or "").strip()
                    elif tag == "ville":
                        city = (child.text or "").strip()
                stations[sid] = {
                    "station_id": sid,
                    "cp": cp,
                    "city": city,
                    "address": address,
                    "pop": elem.attrib.get("pop", ""),
                    "latitude": elem.attrib.get("latitude", ""),
                    "longitude": elem.attrib.get("longitude", ""),
                    "last_seen_year": year,
                }
                elem.clear()
    return stations


def fetch_brand(station_id: str, *, timeout: int = 30) -> tuple[str | None, str | None]:
    url = STATION_URL.format(station_id=station_id)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    brand = extract_brand_from_html(raw)
    if not brand:
        return None, "Marque not found in official station page"
    return brand, None


def load_previous(path: Path) -> dict:
    if not path.exists():
        return {"stations": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry(year: int, output: Path, *, delay: float = 0.08) -> dict:
    previous = load_previous(output)
    previous_stations = dict(previous.get("stations") or {})
    current = current_corsica_stations(year)
    checked_at = datetime.now(timezone.utc).isoformat()

    stations = dict(previous_stations)
    errors: dict[str, str] = {}
    refreshed = 0
    brand_counts: dict[str, int] = {}

    for idx, sid in enumerate(sorted(current)):
        meta = current[sid]
        brand_raw, error = fetch_brand(sid)
        old = stations.get(sid) or {}
        if brand_raw is None and old.get("brand"):
            brand_raw = old.get("brand")
        brand_group = canonical_brand(brand_raw)
        entry = {
            **old,
            **meta,
            "brand": brand_raw,
            "brand_group": brand_group,
            "source_url": STATION_URL.format(station_id=sid),
            "checked_at": checked_at,
            "active_current_year": True,
        }
        if error:
            entry["last_fetch_error"] = error
            errors[sid] = error
        else:
            entry.pop("last_fetch_error", None)
            refreshed += 1
        stations[sid] = entry
        if brand_group:
            brand_counts[brand_group] = brand_counts.get(brand_group, 0) + 1
        if delay and idx + 1 < len(current):
            time.sleep(delay)

    current_ids = set(current)
    for sid, entry in stations.items():
        if sid not in current_ids:
            entry["active_current_year"] = False

    registry = {
        "schema": "a4c-corsica-station-brands-v1",
        "generated_at": checked_at,
        "source": {
            "station_ids": f"official annual XML {year}",
            "brand": "official prix-carburants.gouv.fr station details HTML",
            "station_url_template": STATION_URL,
            "note": "The annual open-data XML does not expose the brand; the official station page does.",
        },
        "current_year": year,
        "current_station_count": len(current),
        "refreshed_brand_count": refreshed,
        "fetch_error_count": len(errors),
        "brand_counts_current": dict(sorted(brand_counts.items())),
        "stations": dict(sorted(stations.items())),
    }
    return registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=0.08)
    parser.add_argument("--max-errors", type=int, default=10)
    args = parser.parse_args()

    registry = build_registry(args.year, args.output, delay=args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "current_station_count": registry["current_station_count"],
        "refreshed_brand_count": registry["refreshed_brand_count"],
        "fetch_error_count": registry["fetch_error_count"],
        "brand_counts_current": registry["brand_counts_current"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))

    if registry["fetch_error_count"] > args.max_errors:
        raise SystemExit(
            f"Too many official station pages could not be classified: "
            f"{registry['fetch_error_count']} > {args.max_errors}"
        )


if __name__ == "__main__":
    main()
