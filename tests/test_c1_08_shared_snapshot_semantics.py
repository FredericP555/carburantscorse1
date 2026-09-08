from __future__ import annotations

from copy import deepcopy
import csv
import gzip
from pathlib import Path
import tempfile
import unittest

import shared_snapshot_semantics as semantics


FIELDS = ["source_year", "station_id", "department", "fuel", "date"]


def _rows():
    rows = []
    sid = 1000
    for department in ("13", "20"):
        for fuel in ("Gazole", "SP95", "E10"):
            sid += 1
            rows.append({
                "source_year": "2026",
                "station_id": str(sid),
                "department": department,
                "fuel": fuel,
                "date": "2026-09-07",
            })
    return rows


def _meta(rows):
    by_department = {"13": 3, "20": 3}
    by_fuel = {"Gazole": 2, "SP95": 2, "E10": 2}
    return {
        "rows": len(rows),
        "min_date": "2026-09-07",
        "max_date": "2026-09-07",
        "years": [2026],
        "departments": ["13", "20"],
        "fuels": ["E10", "Gazole", "SP95"],
        "rows_by_year": {"2026": len(rows)},
        "rows_by_department": by_department,
        "rows_by_fuel": by_fuel,
    }


def _bouclier():
    return {
        "Gazole": {
            "ranges": [{"d1": "2026-04-08", "d2": "2026-04-20"}],
            "phases": [{"d1": "2026-04-08", "d2": "2026-04-20", "cap": 2.25, "phase_id": "g"}],
            "current_active": False,
            "current_active_since": None,
            "current_cap": 2.25,
        },
        "SP95": {
            "ranges": [{"d1": "2026-04-08", "d2": "2026-04-20"}],
            "phases": [{"d1": "2026-04-08", "d2": "2026-04-20", "cap": 1.99, "phase_id": "s"}],
            "current_active": False,
            "current_active_since": None,
            "current_cap": 1.99,
        },
    }


class SharedSnapshotSemanticsTests(unittest.TestCase):
    def _write(self, path: Path, rows) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_valid_manifest_matches_decoded_snapshot(self):
        rows = _rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official.csv.gz"
            self._write(path, rows)
            semantics.validate_snapshot_semantics(_meta(rows), path)

    def test_header_only_snapshot_is_rejected_even_if_manifest_claims_rows(self):
        rows = _rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official.csv.gz"
            self._write(path, [])
            with self.assertRaises(RuntimeError):
                semantics.validate_snapshot_semantics(_meta(rows), path)

    def test_false_manifest_max_date_is_rejected(self):
        rows = _rows()
        meta = _meta(rows)
        meta["max_date"] = "2099-01-01"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official.csv.gz"
            self._write(path, rows)
            with self.assertRaises(RuntimeError):
                semantics.validate_snapshot_semantics(meta, path)

    def test_missing_shield_ranges_are_rejected(self):
        good = _bouclier()
        semantics.validate_bouclier_semantics(good, "2026-09-07")
        bad = deepcopy(good)
        bad["Gazole"].pop("ranges")
        with self.assertRaises(RuntimeError):
            semantics.validate_bouclier_semantics(bad, "2026-09-07")

    def test_phase_outside_effective_range_is_rejected(self):
        bad = _bouclier()
        bad["SP95"]["phases"][0]["d1"] = "2026-03-01"
        with self.assertRaises(RuntimeError):
            semantics.validate_bouclier_semantics(bad, "2026-09-07")


if __name__ == "__main__":
    unittest.main()
