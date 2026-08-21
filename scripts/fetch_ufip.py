#!/usr/bin/env python3
"""Download UFIP Rotterdam Gazole once in C1 and write shared observed + daily CSVs."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole

# Keep the fixed 2026 calibration observations available in future years while still
# avoiding an unnecessarily older export. In 2026 the normal Jan-1 start is retained;
# from 2027 onward the shared series starts on 2026-04-01, before every calibration date.
CALIBRATION_HISTORY_START = date(2026, 4, 1)


def parse_iso(raw: str) -> date:
    return date.fromisoformat(raw)


def default_start(day: date | None = None) -> date:
    day = day or date.today()
    current_year_start = date(day.year, 1, 1)
    return min(current_year_start, CALIBRATION_HISTORY_START)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=parse_iso, default=default_start())
    parser.add_argument("--end", type=parse_iso, default=date.today())
    parser.add_argument("--output-dir", default="outputs/ufip")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    observed = fetch_rotterdam_gazole(args.start, args.end)
    daily = expand_daily(observed, args.start, args.end)
    observed.to_csv(out / "rotterdam_gazole_observed.csv", index=False)
    daily.to_csv(out / "rotterdam_gazole_daily.csv", index=False)
    print(f"UFIP observed rows: {len(observed):,}; daily calendar rows: {len(daily):,}")
    if not observed.empty:
        print(f"UFIP range: {observed['date'].min()} -> {observed['date'].max()}")


if __name__ == "__main__":
    main()
