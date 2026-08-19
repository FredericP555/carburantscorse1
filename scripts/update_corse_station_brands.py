#!/usr/bin/env python3
"""Build the minimal A4C Corsica station-brand registry.

The official price feed already carries station ID, address, commune, coordinates and prices.
This registry deliberately does NOT duplicate those fields. It only adds what the price feed
lacks and what A4C needs analytically:

    station_id -> official brand -> A4C segment/detail

Current station IDs come from the Ministry instantaneous fuel-price dataset. The brand comes
from the official prix-carburants.gouv.fr station page (``Marque : ...``). Historical station
IDs already present in the registry are preserved so older series remain classifiable.

A4C segmentation is explicitly analytical, not an official legal/capital-ownership category:
- gms_lowcost: GMS + discount formats of majors (Total Access, Esso Express)
- traditionnel: classic network formats (Total, ENI, VITO, Avia, etc.)
- inconnu: missing/unresolved brand; excluded from network comparisons

Manual corrections in config/corse_station_brand_corrections.csv override automatic
classification. ID corrections override brand corrections.
"""
from __future__ import annotations

import argparse
import csv
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
DEFAULT_CORRECTIONS = ROOT / "config" / "corse_station_brand_corrections.csv"
STATION_URL = "https://www.prix-carburants.gouv.fr/station/{station_id}"
INSTANT_API = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "prix-des-carburants-en-france-flux-instantane-v2/records"
)
USER_AGENT = "A4C-observatoire-station-brands/2.0"
API_PAGE_SIZE = 100
API_WORKERS = 6
BRAND_WORKERS = 4

GMS = [
    "leclerc", "e.leclerc", "intermarche", "carrefour", "super u", "hyper u",
    "u express", "systeme u", "auchan", "casino", "geant", "cora", "netto",
    "colruyt", "match", "leader price", "monoprix", "simply", "atac", "bi1",
]
LOW_COST_MAJORS = ["total access", "totalenergies access", "esso express"]
MAJORS = [
    "total", "totalenergies", "elan", "esso", "shell", "bp", "agip", "eni", "mobil",
]
SEGMENTS = {"gms_lowcost", "traditionnel", "inconnu"}
DETAILS = {
    "gms", "lowcost_major", "major_tradi", "marque_tradi",
    "sans_enseigne_verifiee", "inconnu",
}


class TextTokens(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).casefold().strip()
    for src, dst in (
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("â", "a"), ("ä", "a"),
        ("î", "i"), ("ï", "i"),
        ("ô", "o"), ("ö", "o"),
        ("û", "u"), ("ù", "u"), ("ü", "u"),
        ("ç", "c"), ("’", "'"),
    ):
        text = text.replace(src, dst)
    return " ".join(text.split())


def extract_brand_from_html(raw: str) -> str | None:
    """Extract the official ``Marque`` value from one station detail page."""
    parser = TextTokens()
    parser.feed(raw)
    tokens = [html.unescape(token).strip() for token in parser.tokens if token.strip()]
    for idx, token in enumerate(tokens):
        compact = re.sub(r"\s+", " ", token).strip()
        match = re.match(r"^Marque\s*:\s*(.*)$", compact, flags=re.I)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline:
            return inline
        for nxt in tokens[idx + 1 : idx + 5]:
            if nxt.strip():
                return nxt.strip()
    return None


def classify_brand(brand: str | None) -> tuple[str, str]:
    """Return A4C (segment, detail) from the official brand only."""
    normalized = _norm(brand)
    if not normalized:
        return "inconnu", "inconnu"
    # Discount must be tested before majors: Total Access before Total.
    if any(_norm(candidate) in normalized for candidate in LOW_COST_MAJORS):
        return "gms_lowcost", "lowcost_major"
    if any(_norm(candidate) in normalized for candidate in GMS):
        return "gms_lowcost", "gms"
    if any(_norm(candidate) in normalized for candidate in MAJORS):
        return "traditionnel", "major_tradi"
    return "traditionnel", "marque_tradi"


def load_corrections(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Load justified corrections; station-ID corrections take precedence later."""
    by_id: dict[str, dict] = {}
    by_brand: dict[str, dict] = {}
    if not path.exists():
        return by_id, by_brand

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"cle", "segment", "detail", "justification"}
        if not reader.fieldnames or not required.issubset({x.strip() for x in reader.fieldnames}):
            raise RuntimeError(f"Invalid correction file header: {path}")
        for row in reader:
            key = (row.get("cle") or "").strip()
            if not key:
                continue
            segment = (row.get("segment") or "").strip()
            detail = (row.get("detail") or "").strip()
            justification = (row.get("justification") or "").strip()
            if segment not in SEGMENTS:
                raise RuntimeError(f"Unknown correction segment {segment!r} for {key!r}")
            if detail not in DETAILS:
                raise RuntimeError(f"Unknown correction detail {detail!r} for {key!r}")
            if not justification:
                raise RuntimeError(f"Missing correction justification for {key!r}")
            value = {"segment": segment, "detail": detail, "justification": justification}
            if key.isdigit():
                by_id[key] = value
            else:
                by_brand[_norm(key)] = value
    return by_id, by_brand


def classify_station(
    station_id: str,
    brand: str | None,
    by_id: dict[str, dict],
    by_brand: dict[str, dict],
) -> tuple[str, str, str]:
    """Classify one station, applying brand correction then stronger ID correction."""
    segment, detail = classify_brand(brand)
    source = "auto"
    brand_correction = by_brand.get(_norm(brand))
    if brand_correction:
        segment, detail = brand_correction["segment"], brand_correction["detail"]
        source = "correction_marque"
    id_correction = by_id.get(station_id)
    if id_correction:
        segment, detail = id_correction["segment"], id_correction["detail"]
        source = "correction_id"
    return segment, detail, source


def _request_bytes(url: str, *, timeout: int = 20, attempts: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _instant_api_page(offset: int) -> dict:
    # Only ID + postal code are needed here; the price feed already owns all other station data.
    params = urllib.parse.urlencode(
        {"select": "id,cp", "order_by": "id", "limit": API_PAGE_SIZE, "offset": offset}
    )
    payload = json.loads(_request_bytes(f"{INSTANT_API}?{params}", timeout=25).decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RuntimeError("Unexpected response from official instantaneous fuel API")
    return payload


def _add_corsica_ids(target: set[str], rows: list[dict]) -> None:
    for row in rows:
        cp = str(row.get("cp") or "").strip().zfill(5)
        if not cp.startswith("20"):
            continue
        station_id = str(row.get("id") or "").strip()
        if station_id:
            target.add(station_id)


def current_corsica_station_ids() -> set[str]:
    """Return only current Corsica station IDs from the official instantaneous dataset."""
    first = _instant_api_page(0)
    total_count = int(first.get("total_count") or 0)
    if total_count <= 0:
        raise RuntimeError("Official instantaneous fuel API returned no stations")

    station_ids: set[str] = set()
    _add_corsica_ids(station_ids, first["results"])
    offsets = list(range(API_PAGE_SIZE, total_count, API_PAGE_SIZE))
    if offsets:
        with ThreadPoolExecutor(max_workers=API_WORKERS) as executor:
            for payload in executor.map(_instant_api_page, offsets):
                _add_corsica_ids(station_ids, payload["results"])
    if not station_ids:
        raise RuntimeError("No Corsica station found in official instantaneous fuel API")
    return station_ids


def fetch_brand(station_id: str, *, timeout: int = 12) -> tuple[str | None, str | None]:
    """Fetch one official station page and return the displayed brand."""
    try:
        raw = _request_bytes(STATION_URL.format(station_id=station_id), timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    brand = extract_brand_from_html(raw.decode("utf-8", errors="replace"))
    return (brand, None) if brand else (None, "Marque not found in official station page")


def _normalize_previous_entry(raw: dict) -> dict:
    """Accept both the former verbose v1 registry and the compact v2 registry."""
    brand = raw.get("enseigne")
    if brand is None:
        brand = raw.get("brand") or ""
    active = raw.get("active")
    if active is None:
        active = raw.get("active_current_year", False)
    verified = raw.get("verified_at") or raw.get("checked_at") or ""
    first_seen = raw.get("first_seen") or (verified[:10] if verified else "")
    last_seen = raw.get("last_seen") or (verified[:10] if active and verified else "")
    segment = raw.get("segment")
    detail = raw.get("detail")
    if not segment or not detail:
        segment, detail = classify_brand(brand)
    return {
        "enseigne": brand,
        "segment": segment,
        "detail": detail,
        "classification_source": raw.get("classification_source", "auto"),
        "active": bool(active),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "verified_at": verified,
    }


def load_previous(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(station_id): _normalize_previous_entry(entry)
        for station_id, entry in (payload.get("stations") or {}).items()
    }


def build_registry(output: Path, corrections: Path, *, delay: float = 0.05) -> dict:
    previous = load_previous(output)
    by_id, by_brand = load_corrections(corrections)
    current_ids = current_corsica_station_ids()
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    def fetch_one(station_id: str):
        result = fetch_brand(station_id)
        if delay:
            time.sleep(delay)
        return station_id, result

    with ThreadPoolExecutor(max_workers=BRAND_WORKERS) as executor:
        fetched = dict(executor.map(fetch_one, sorted(current_ids)))

    stations: dict[str, dict] = {}
    errors: dict[str, str] = {}
    verified_count = 0

    for station_id in sorted(current_ids | set(previous)):
        old = previous.get(station_id) or {}
        if station_id in current_ids:
            brand, error = fetched[station_id]
            if brand:
                verified_count += 1
                brand_source = "officiel"
                verified_at = now
            else:
                errors[station_id] = error or "unknown fetch error"
                brand = old.get("enseigne") or ""
                brand_source = "herite" if brand else "non_resolu"
                verified_at = old.get("verified_at", "")

            segment, detail, classification_source = classify_station(
                station_id, brand, by_id, by_brand
            )
            stations[station_id] = {
                "enseigne": brand,
                "segment": segment,
                "detail": detail,
                "classification_source": classification_source,
                "brand_source": brand_source,
                "active": True,
                "first_seen": old.get("first_seen") or today,
                "last_seen": today,
                "verified_at": verified_at,
            }
        else:
            # Historical ID: preserve its last known brand and classification. A current manual
            # correction may still deliberately override that inherited classification.
            brand = old.get("enseigne") or ""
            segment = old.get("segment") or "inconnu"
            detail = old.get("detail") or "inconnu"
            classification_source = old.get("classification_source", "auto")
            if _norm(brand) in by_brand:
                corr = by_brand[_norm(brand)]
                segment, detail, classification_source = (
                    corr["segment"], corr["detail"], "correction_marque"
                )
            if station_id in by_id:
                corr = by_id[station_id]
                segment, detail, classification_source = (
                    corr["segment"], corr["detail"], "correction_id"
                )
            stations[station_id] = {
                "enseigne": brand,
                "segment": segment,
                "detail": detail,
                "classification_source": classification_source,
                "brand_source": "herite",
                "active": False,
                "first_seen": old.get("first_seen", ""),
                "last_seen": old.get("last_seen", ""),
                "verified_at": old.get("verified_at", ""),
            }

    current_entries = [entry for entry in stations.values() if entry["active"]]
    segment_counts = {
        segment: sum(1 for entry in current_entries if entry["segment"] == segment)
        for segment in sorted(SEGMENTS)
    }
    detail_counts: dict[str, int] = {}
    for entry in current_entries:
        detail_counts[entry["detail"]] = detail_counts.get(entry["detail"], 0) + 1

    return {
        "schema": "a4c-corsica-station-brands-v2",
        "generated_at": now,
        "source": {
            "station_ids": "official Ministry instantaneous fuel-price API",
            "station_dataset": "prix-des-carburants-en-france-flux-instantane-v2",
            "enseigne": "official prix-carburants.gouv.fr station detail HTML",
            "note": "The price feed already owns address/commune/coordinates; this registry only adds brand and A4C classification.",
        },
        "classification": {
            "segments": ["gms_lowcost", "traditionnel", "inconnu"],
            "unknown_policy": "inconnu is excluded from network comparisons",
            "corrections_file": str(corrections.relative_to(ROOT)) if corrections.is_relative_to(ROOT) else str(corrections),
        },
        "current_station_count": len(current_ids),
        "verified_brand_count": verified_count,
        "fetch_error_count": len(errors),
        "unresolved_current_count": sum(
            1 for entry in current_entries if entry["segment"] == "inconnu"
        ),
        "segment_counts_current": segment_counts,
        "detail_counts_current": dict(sorted(detail_counts.items())),
        "stations": stations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--max-errors", type=int, default=10)
    args = parser.parse_args()

    registry = build_registry(args.output, args.corrections, delay=args.delay)
    summary = {
        key: registry[key]
        for key in (
            "current_station_count", "verified_brand_count", "fetch_error_count",
            "unresolved_current_count", "segment_counts_current", "detail_counts_current",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Fail closed: never replace the persisted registry when collection quality is too poor.
    if registry["fetch_error_count"] > args.max_errors:
        raise SystemExit(
            f"Too many official station pages failed: "
            f"{registry['fetch_error_count']} > {args.max_errors}; registry unchanged"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
