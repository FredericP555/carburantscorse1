#!/usr/bin/env python3
"""Persist station-brand policy metadata even when no station identity changes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from resolve_corse_station_brands_incremental import (
    BRAND_REVERIFY_DAYS,
    BRAND_REVERIFY_LIMIT,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "corse_station_brands.json"


def ensure_policy_metadata(payload: dict) -> tuple[dict, bool]:
    """Return a copy carrying the current reverification policy and whether it changed."""
    updated = dict(payload)
    classification = dict(updated.get("classification") or {})
    classification["brand_reverify_days"] = BRAND_REVERIFY_DAYS
    classification["brand_reverify_limit_per_run"] = BRAND_REVERIFY_LIMIT
    updated["classification"] = classification
    return updated, updated != payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    updated, changed = ensure_policy_metadata(payload)
    if not changed:
        print("Station-brand policy metadata already current.")
        return

    args.path.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Updated station-brand policy metadata: "
        f"reverify_days={BRAND_REVERIFY_DAYS}, limit={BRAND_REVERIFY_LIMIT}"
    )


if __name__ == "__main__":
    main()
