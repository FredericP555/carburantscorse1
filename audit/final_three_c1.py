#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update_data_v2 import download  # noqa: E402

TARGET_IDS = {"20213003", "20213007", "20213008"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def audit_folelli() -> dict:
    result: dict[str, object] = {"years": {}, "station_pages": {}}
    for year in (2025, 2026):
        raw = download(year)
        zf = zipfile.ZipFile(io.BytesIO(raw))
        name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        found: dict[str, dict] = {}
        with zf.open(name) as fh:
            for _, elem in ET.iterparse(fh, events=("end",)):
                if _local(elem.tag) != "pdv":
                    continue
                sid = str(elem.attrib.get("id") or "")
                if sid not in TARGET_IDS:
                    elem.clear()
                    continue
                prices = []
                address = None
                city = None
                for child in list(elem):
                    tag = _local(child.tag)
                    if tag == "adresse":
                        address = " ".join("".join(child.itertext()).split()) or None
                    elif tag == "ville":
                        city = " ".join("".join(child.itertext()).split()) or None
                    elif tag == "prix":
                        maj = child.attrib.get("maj")
                        if maj:
                            prices.append({
                                "fuel": child.attrib.get("nom"),
                                "maj": maj,
                                "value": child.attrib.get("valeur"),
                            })
                found[sid] = {
                    "id": sid,
                    "cp": elem.attrib.get("cp"),
                    "pop": elem.attrib.get("pop"),
                    "latitude": elem.attrib.get("latitude"),
                    "longitude": elem.attrib.get("longitude"),
                    "address": address,
                    "city": city,
                    "price_count": len(prices),
                    "first_price": min((p["maj"] for p in prices), default=None),
                    "last_price": max((p["maj"] for p in prices), default=None),
                    "fuels": sorted({str(p["fuel"]) for p in prices if p.get("fuel")}),
                }
                elem.clear()
        result["years"][str(year)] = found

    for sid in sorted(TARGET_IDS):
        url = f"https://www.prix-carburants.gouv.fr/station/{sid}"
        request = urllib.request.Request(url, headers={"User-Agent": "A4C-final-audit/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8", errors="replace")
                compact = " ".join(re.sub(r"<[^>]+>", " ", text).split())
                anchors = []
                for needle in ("Folelli", "Marque", "Adresse", "Total"):
                    pos = compact.casefold().find(needle.casefold())
                    if pos >= 0:
                        anchors.append(compact[max(0, pos - 100): pos + 220])
                result["station_pages"][sid] = {
                    "status": getattr(response, "status", None),
                    "final_url": response.geturl(),
                    "snippets": anchors[:6],
                }
        except urllib.error.HTTPError as exc:
            result["station_pages"][sid] = {"status": exc.code, "error": str(exc)}
        except Exception as exc:
            result["station_pages"][sid] = {"status": None, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


class CanvasParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canvases: list[dict[str, str]] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag.casefold() == "canvas":
            self.canvases.append(values)


def _num(value: str | None) -> int | None:
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def audit_canvas(paths: list[str]) -> dict:
    reports = {}
    for raw_path in paths:
        path = Path(raw_path)
        parser = CanvasParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        duplicates = sorted(k for k, n in Counter(parser.ids).items() if n > 1)
        canvases = []
        for item in parser.canvases:
            width = _num(item.get("width"))
            height = _num(item.get("height"))
            style = item.get("style") or ""
            css_w = _num(re.search(r"width:\s*([^;]+)", style).group(1)) if re.search(r"width:\s*([^;]+)", style) else None
            css_h = _num(re.search(r"height:\s*([^;]+)", style).group(1)) if re.search(r"height:\s*([^;]+)", style) else None
            canvases.append({
                "id": item.get("id"),
                "width_attr": width,
                "height_attr": height,
                "css_width": css_w,
                "css_height": css_h,
                "style": style,
            })
        assert len(canvases) >= 2, (path, canvases)
        assert not duplicates, (path, duplicates)
        for canvas in canvases[:2]:
            w = canvas["css_width"] or canvas["width_attr"]
            h = canvas["css_height"] or canvas["height_attr"]
            assert w is not None and w >= 300, (path, canvas)
            assert h is not None and h >= 140, (path, canvas)
        reports[path.name] = {"canvas_count": len(canvases), "duplicate_ids": duplicates, "canvases": canvases}

    groups: dict[str, list[dict]] = {}
    for name, report in reports.items():
        key = re.sub(r"-[12]\.html$", "", name)
        groups.setdefault(key, []).append(report)
    for key, reps in groups.items():
        assert len(reps) == 2, (key, len(reps))
        a, b = reps
        assert len(a["canvases"]) == len(b["canvases"]), key
        for ca, cb in zip(a["canvases"][:2], b["canvases"][:2]):
            for field in ("width_attr", "height_attr", "css_width", "css_height"):
                va, vb = ca.get(field), cb.get(field)
                if va is None or vb is None:
                    continue
                tolerance = max(2, round(max(va, vb) * 0.03))
                assert abs(va - vb) <= tolerance, (key, field, va, vb, tolerance)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("folelli")
    canvas = sub.add_parser("canvas")
    canvas.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.cmd == "folelli":
        audit_folelli()
    else:
        audit_canvas(args.paths)


if __name__ == "__main__":
    main()
