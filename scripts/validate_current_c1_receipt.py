#!/usr/bin/env python3
"""Accept a prior C1 business-success receipt only if it still proves current content."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

try:
    from scripts import verify_c1_business_success as business
except ImportError:  # direct execution as python scripts/validate_current_c1_receipt.py
    import verify_c1_business_success as business


def validate_current_receipt(
    receipt: dict,
    *,
    expected_tag: str,
    current_data: bytes,
    pages_data: bytes,
) -> None:
    if receipt.get("status") != "business-success":
        raise ValueError("receipt status is not business-success")
    if receipt.get("release_tag") != expected_tag:
        raise ValueError("receipt release tag does not match expected release")

    current_sha = business.sha256_bytes(current_data)
    pages_sha = business.sha256_bytes(pages_data)
    if receipt.get("expected_sha256") != current_sha:
        raise ValueError("receipt expected hash no longer matches current repository data.json")
    if receipt.get("pages_sha256") != current_sha:
        raise ValueError("receipt-certified Pages hash differs from current repository data.json")
    if receipt.get("release_data_sha256") != current_sha:
        raise ValueError("receipt-certified release target hash differs from current repository data.json")
    if pages_sha != current_sha:
        raise ValueError("currently served Pages data.json differs from current repository data.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", required=True)
    p.add_argument("--expected-tag", required=True)
    p.add_argument("--current-data", default="data.json")
    p.add_argument("--pages-data-file")
    p.add_argument("--page-url", default=business.DEFAULT_PAGE_URL)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    current_data = Path(args.current_data).read_bytes()
    if args.pages_data_file:
        pages_data = Path(args.pages_data_file).read_bytes()
    else:
        stamp = int(time.time() * 1000)
        pages_data = business.fetch_public(
            business._cache_busted_url(args.page_url, stamp)
        )
    validate_current_receipt(
        receipt,
        expected_tag=args.expected_tag,
        current_data=current_data,
        pages_data=pages_data,
    )
    print("C1 business-success receipt still matches current repository and Pages content")


if __name__ == "__main__":
    main()
