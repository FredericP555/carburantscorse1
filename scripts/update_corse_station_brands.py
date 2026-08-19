#!/usr/bin/env python3
"""Build the authoritative Corsica station -> brand registry from official sources.

The Ministry's instantaneous open-data API supplies the current station IDs and metadata.
The open-data record deliberately has no brand field, while the official
prix-carburants.gouv.fr station detail page exposes the brand as ``Marque : ...``.
The registry joins those two official sources on the station ID.

The registry is append-preserving: stations seen in previous runs remain in the file, while
stations currently present in the instantaneous feed are refreshed. This keeps historical IDs
available if a station closes, changes identifier or changes brand later.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "config" / "corse_station_brands.json"
STATION_URL = "https://www.prix-carburants.gouv.fr/station/{station_id}"
INSTANT_API = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "prix-des-carburants-en-france-flux-instantane-v2/records"
)
USER_AGENT = "A4C-observatoire-station-brands/1.2"
API_PAGE_SIZE = 100
API_WORKERS = 6
BRAND_WORKERS = 4


class TextTokens(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)


def extract_brand_from_html(raw: str) -> str | None:
    """Extract the official ``Marque`` value from one station detail page."""
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
    """Group only the brands for which A4C needs a stable family name."""
    if not raw:
        return None
    value = " ".join(raw.split()).strip()
    folded = value.casefold()
    if folded.startswith("totalenergies") or folded.startswith("total energies") or folded == "total":
        return "TotalEnergies"
    if folded.startswith("vito"):
        return "VITO"
    if folded == "eni" or folded.startswith("eni "):
        return "ENI"
    return value


def _request_bytes(url: str, *, timeout: int = 20, attempts: int = 2) -> bytes:
    """Small retry wrapper for the two official HTTP sources."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _instant_api_page(offset: int) -> dict:
    params = urllib.parse.urlencode(
        {
            "select": "id,latitude,longitude,cp,pop,adresse,ville",
            "order_by": "id",
            "limit": API_PAGE_SIZE,
            "offset": offset,
        }
    )
    raw = _request_bytes(f"{INSTANT_API}?{params}", timeout=25)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RuntimeError("Unexpected response from official instantaneous fuel API")
    return payload


def _add_corsica_rows(stations: dict[str, dict], rows: list[dict]) -> None:
    for row in rows:
        cp = str(row.get("cp") or "").strip().zfill(5)
        if not cp.startswith("20"):
            continue
        sid = str(row.get("id") or "").strip()
        if not sid:
            continue
        stations[sid] = {
            "station_id": sid,
            "cp": cp,
            "city": str(row.get("ville") or "").strip(),
            "address": str(row.get("adresse") or "").strip(),
            "pop": str(row.get("pop") or "").strip(),
            "latitude": str(row.get("latitude") or "").strip(),
            "longitude": str(row.get("longitude") or "").strip(),
            "last_seen_year": date.today().year,
        }


def current_corsica_stations() -> dict[str, dict]:
    """Return current Corsica PDVs from the official instantaneous dataset, keyed by ID."""
    first = _instant_api_page(0)
    total_count = int(first.get("total_count") or 0)
    if total_count <= 0:
        raise RuntimeError("Official instantaneous fuel API returned no stations")

    stations: dict[str, dict] = {}
    _add_corsica_rows(stations, first["results"])
    offsets = list(range(API_PAGE_SIZE, total_count, API_PAGE_SIZE))
    if offsets:
        with ThreadPoolExecutor(max_workers=API_WORKERS) as executor:
            for payload in executor.map(_instant_api_page, offsets):
                _add_corsica_rows(stations, payload["results"])

    if not stations:
        raise RuntimeError("No Corsica station found in official instantaneous fuel API")
    return stations


def fetch_brand(station_id: str, *, timeout: int = 12) -> tuple[str | None, str | None]:
    """Fetch the official station page and return its displayed brand."""
    url = STATION_URL.format(station_id=station_id)
    try:
        raw_bytes = _request_bytes(url, timeout=timeout)
        raw = raw_bytes.decode("utf-8", errors="replace")
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


def build_registry(output: Path, *, delay: float = 0.05) -> dict:
    previous = load_previous(output)
    previous_stations = dict(previous.get("stations") or {})
    current = current_corsica_stations()
    checked_at = datetime.now(timezone.utc).isoformat()

    stations = dict(previous_stations)
    errors: dict[str, str] = {}
    refreshed = 0
    brand_counts: dict[str, int] = {}
    ids = sorted(current)

    def fetch_one(sid: str):
        result = fetch_brand(sid)
        if delay:
            time.sleep(delay)
        return sid, result

    with ThreadPoolExecutor(max_workers=BRAND_WORKERS) as executor:
        brand_results = dict(executor.map(fetch_one, ids))

    for sid in ids:
        meta = current[sid]
        brand_raw, error = brand_results[sid]
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

    current_ids = set(current)
    for sid, entry in stations.items():
        if sid not in current_ids:
            entry["active_current_year"] = False

    return {
        "schema": "a4c-corsica-station-brands-v1",
        "generated_at": checked_at,
        "source": {
            "station_ids": "official Ministry instantaneous fuel-price API",
            "station_dataset": "prix-des-carburants-en-france-flux-instantane-v2",
            "brand": "official prix-carburants.gouv.fr station detail HTML",
            "station_url_template": STATION_URL,
            "note": "The open-data feed has no brand field; the official station page displays Marque. Both are joined on station_id.",
        },
        "current_year": date.today().year,
        "current_station_count": len(current),
        "refreshed_brand_count": refreshed,
        "fetch_error_count": len(errors),
        "brand_counts_current": dict(sorted(brand_counts.items())),
        "stations": dict(sorted(stations.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--max-errors", type=int, default=10)
    args = parser.parse_args()

    registry = build_registry(args.output, delay=args.delay)
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
