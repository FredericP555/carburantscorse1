#!/usr/bin/env python3
"""Verify that GitHub Pages really serves the C1 data promoted on ``main``.

A green production workflow is not enough: business success requires the public
``data.json`` to be byte-for-byte identical to the repository copy that was validated.
The verifier retries while Pages may still be deploying, then fails closed.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request

DEFAULT_PAGE_URL = "https://fredericp555.github.io/carburantscorse1/data.json"


class BusinessSuccessError(RuntimeError):
    """Raised when the public publication cannot be proven identical to expected data."""


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _decode_payload(blob: bytes, label: str) -> tuple[dict, str]:
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BusinessSuccessError(f"{label} is not UTF-8 JSON") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BusinessSuccessError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise BusinessSuccessError(f"{label} JSON root is not an object")
    raw_date = (payload.get("meta") or {}).get("last_date")
    if not raw_date:
        raise BusinessSuccessError(f"{label} has no meta.last_date")
    try:
        parsed = date.fromisoformat(str(raw_date))
    except ValueError as exc:
        raise BusinessSuccessError(f"{label} has invalid meta.last_date={raw_date!r}") from exc
    return payload, parsed.isoformat()


def evaluate_publication(
    expected_bytes: bytes,
    pages_bytes: bytes,
    *,
    expected_commit: str,
    page_url: str,
    release_tag: str | None = None,
) -> dict:
    """Compare one public Pages response with the expected repository bytes."""
    _expected, expected_date = _decode_payload(expected_bytes, "expected data.json")
    _pages, pages_date = _decode_payload(pages_bytes, "Pages data.json")
    expected_sha = sha256_bytes(expected_bytes)
    pages_sha = sha256_bytes(pages_bytes)

    if pages_sha != expected_sha:
        raise BusinessSuccessError(
            "Pages data.json differs from expected main data.json: "
            f"expected_sha={expected_sha}, pages_sha={pages_sha}, "
            f"expected_date={expected_date}, pages_date={pages_date}"
        )
    if pages_date != expected_date:
        # Kept as an explicit business invariant even though identical bytes normally
        # imply an identical date. This makes the intended contract visible and testable.
        raise BusinessSuccessError(
            f"Pages business date {pages_date} != expected business date {expected_date}"
        )

    return {
        "status": "business-success",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "commit": expected_commit,
        "release_tag": release_tag,
        "page_url": page_url,
        "expected_sha256": expected_sha,
        "pages_sha256": pages_sha,
        "expected_data_through": expected_date,
        "pages_data_through": pages_date,
    }


def _cache_busted_url(url: str, attempt: int) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("a4c_verify", f"{int(time.time() * 1000)}-{attempt}"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_public(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "A4C-C1-business-success/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise BusinessSuccessError(f"Pages returned HTTP {status}")
        return response.read()


def wait_for_publication(
    expected_bytes: bytes,
    *,
    page_url: str,
    expected_commit: str,
    release_tag: str | None = None,
    timeout_seconds: float = 240,
    interval_seconds: float = 5,
    fetcher: Callable[[str], bytes] = fetch_public,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Poll Pages until exact expected bytes are served or the deadline expires."""
    if timeout_seconds < 0 or interval_seconds < 0:
        raise ValueError("timeout and interval must be non-negative")
    start = monotonic()
    attempts = 0
    last_error: Exception | None = None

    while True:
        attempts += 1
        try:
            public_url = _cache_busted_url(page_url, attempts)
            pages_bytes = fetcher(public_url)
            receipt = evaluate_publication(
                expected_bytes,
                pages_bytes,
                expected_commit=expected_commit,
                page_url=page_url,
                release_tag=release_tag,
            )
            receipt["attempts"] = attempts
            return receipt
        except Exception as exc:  # network lag and stale Pages are both retryable here
            last_error = exc

        elapsed = monotonic() - start
        if elapsed >= timeout_seconds:
            raise BusinessSuccessError(
                f"C1 business success not proven after {attempts} attempts / "
                f"{elapsed:.1f}s: {last_error}"
            ) from last_error
        sleeper(interval_seconds)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception as exc:
        raise BusinessSuccessError("cannot determine checked-out commit") from exc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--expected", default="data.json")
    p.add_argument("--page-url", default=DEFAULT_PAGE_URL)
    p.add_argument("--output", default="outputs/c1-business-success.json")
    p.add_argument("--commit", default=None)
    p.add_argument("--release-tag", default=os.environ.get("A4C_RELEASE_TAG"))
    p.add_argument("--timeout-seconds", type=float, default=240)
    p.add_argument("--interval-seconds", type=float, default=5)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    expected_path = Path(args.expected)
    if not expected_path.is_file():
        raise SystemExit(f"Expected data file not found: {expected_path}")
    expected_bytes = expected_path.read_bytes()
    commit = args.commit or _git_head()

    receipt = wait_for_publication(
        expected_bytes,
        page_url=args.page_url,
        expected_commit=commit,
        release_tag=args.release_tag,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
