"""Regression tests for C1 end-to-end publication business success.

These tests define the contract before the verifier implementation exists:
- the public Pages JSON must be byte-for-byte identical to the expected main-branch data.json;
- the published business date must match;
- stale or malformed public content must fail closed;
- temporary Pages lag may be retried, but persistent unavailability must fail.
"""
from __future__ import annotations

import json
import unittest

import verify_c1_business_success as business


def payload(last_date: str, marker: int = 1) -> bytes:
    return json.dumps(
        {
            "meta": {"last_date": last_date},
            "G": {"corse": {"d": [[0, 1.8, 1.593]]}},
            "marker": marker,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class BusinessSuccessEvaluationTests(unittest.TestCase):
    def test_exact_public_copy_is_business_success(self):
        expected = payload("2026-09-06")
        receipt = business.evaluate_publication(
            expected,
            expected,
            expected_commit="abc123",
            page_url="https://example.test/data.json",
            release_tag="a4c-v2-shared-test",
        )
        self.assertEqual(receipt["status"], "business-success")
        self.assertEqual(receipt["expected_sha256"], receipt["pages_sha256"])
        self.assertEqual(receipt["expected_data_through"], "2026-09-06")
        self.assertEqual(receipt["pages_data_through"], "2026-09-06")
        self.assertEqual(receipt["commit"], "abc123")
        self.assertEqual(receipt["release_tag"], "a4c-v2-shared-test")

    def test_stale_pages_copy_fails_even_when_valid_json(self):
        expected = payload("2026-09-06", marker=2)
        stale = payload("2026-08-30", marker=1)
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                expected,
                stale,
                expected_commit="abc123",
                page_url="https://example.test/data.json",
            )

    def test_same_business_date_but_different_bytes_fails(self):
        expected = payload("2026-09-06", marker=1)
        altered = payload("2026-09-06", marker=999)
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                expected,
                altered,
                expected_commit="abc123",
                page_url="https://example.test/data.json",
            )

    def test_malformed_public_json_fails_closed(self):
        expected = payload("2026-09-06")
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                expected,
                b"<html>not json</html>",
                expected_commit="abc123",
                page_url="https://example.test/data.json",
            )

    def test_expected_payload_without_last_date_fails_closed(self):
        bad_expected = b'{"meta":{}}'
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                bad_expected,
                bad_expected,
                expected_commit="abc123",
                page_url="https://example.test/data.json",
            )


class BusinessSuccessPollingTests(unittest.TestCase):
    def test_poll_accepts_pages_after_temporary_stale_copy(self):
        expected = payload("2026-09-06", marker=2)
        stale = payload("2026-08-30", marker=1)
        responses = iter([stale, stale, expected])
        sleeps = []

        receipt = business.wait_for_publication(
            expected,
            page_url="https://example.test/data.json",
            expected_commit="abc123",
            timeout_seconds=30,
            interval_seconds=1,
            fetcher=lambda _url: next(responses),
            sleeper=lambda n: sleeps.append(n),
        )
        self.assertEqual(receipt["status"], "business-success")
        self.assertEqual(receipt["attempts"], 3)
        self.assertEqual(sleeps, [1, 1])

    def test_poll_fails_when_pages_never_match(self):
        expected = payload("2026-09-06", marker=2)
        stale = payload("2026-08-30", marker=1)
        clock = iter([0.0, 0.0, 5.0, 10.0, 15.0])

        with self.assertRaises(business.BusinessSuccessError):
            business.wait_for_publication(
                expected,
                page_url="https://example.test/data.json",
                expected_commit="abc123",
                timeout_seconds=10,
                interval_seconds=1,
                fetcher=lambda _url: stale,
                sleeper=lambda _n: None,
                monotonic=lambda: next(clock),
            )

    def test_poll_retries_transient_fetch_errors(self):
        expected = payload("2026-09-06")
        calls = {"n": 0}

        def fetcher(_url):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("temporary network failure")
            return expected

        receipt = business.wait_for_publication(
            expected,
            page_url="https://example.test/data.json",
            expected_commit="abc123",
            timeout_seconds=30,
            interval_seconds=1,
            fetcher=fetcher,
            sleeper=lambda _n: None,
        )
        self.assertEqual(receipt["attempts"], 3)


if __name__ == "__main__":
    unittest.main()
