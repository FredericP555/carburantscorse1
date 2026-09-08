#!/usr/bin/env python3
"""Download UFIP Rotterdam Gazole once in C1 and write shared observed + daily CSVs.

The UFIP public front door can intermittently return a stripped page to cloud runners. Each
attempt still enforces the full documented source contract; transient failures are retried by
starting the complete request sequence again, which creates a fresh HTTP session in the normal
production path. After the bounded retry budget the job fails closed.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
import time
from typing import Callable

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole

# Keep the fixed 2026 calibration observations available in future years while still
# avoiding an unnecessarily older export. In 2026 the normal Jan-1 start is retained;
# from 2027 onward the shared series starts on 2026-04-01, before every calibration date.
CALIBRATION_HISTORY_START = date(2026, 4, 1)
DEFAULT_ATTEMPTS = 4
DEFAULT_DELAY_SECONDS = 5


def parse_iso(raw: str) -> date:
    return date.fromisoformat(raw)


def default_start(day: date | None = None) -> date:
    day = day or date.today()
    current_year_start = date(day.year, 1, 1)
    return min(current_year_start, CALIBRATION_HISTORY_START)


def fetch_rotterdam_with_retries(
    start_date: date,
    end_date: date,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
    fetcher: Callable[[date, date], pd.DataFrame] = fetch_rotterdam_gazole,
    sleeper: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Retry only known source/transport/parse failures; never weaken semantic validation."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    errors: list[str] = []
    transient = (RuntimeError, ValueError, requests.RequestException)
    for attempt in range(1, attempts + 1):
        try:
            return fetcher(start_date, end_date)
        except transient as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt >= attempts:
                raise RuntimeError(
                    f"UFIP download failed after {attempts} attempts; " + " | ".join(errors)
                ) from exc
            wait = max(0, delay_seconds) * attempt
            print(
                f"WARNING: transient UFIP fetch failure on attempt {attempt}/{attempts}: {exc}; "
                f"retrying in {wait}s",
                file=sys.stderr,
            )
            sleeper(wait)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=parse_iso, default=default_start())
    parser.add_argument("--end", type=parse_iso, default=date.today())
    parser.add_argument("--output-dir", default="outputs/ufip")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--retry-delay", type=int, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    observed = fetch_rotterdam_with_retries(
        args.start,
        args.end,
        attempts=args.attempts,
        delay_seconds=args.retry_delay,
    )
    daily = expand_daily(observed, args.start, args.end)
    observed.to_csv(out / "rotterdam_gazole_observed.csv", index=False)
    daily.to_csv(out / "rotterdam_gazole_daily.csv", index=False)
    print(f"UFIP observed rows: {len(observed):,}; daily calendar rows: {len(daily):,}")
    if not observed.empty:
        print(f"UFIP range: {observed['date'].min()} -> {observed['date'].max()}")


if __name__ == "__main__":
    main()
