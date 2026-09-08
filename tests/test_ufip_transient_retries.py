from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from scripts.fetch_ufip import fetch_rotterdam_with_retries


class UfipTransientRetryTests(unittest.TestCase):
    def test_transient_contract_failures_are_retried_with_fresh_calls(self):
        calls = []
        sleeps = []
        expected = pd.DataFrame({"date": [date(2026, 9, 4)], "rotterdam_eur_l": [1.025]})

        def fetcher(start, end):
            calls.append((start, end))
            if len(calls) < 3:
                raise RuntimeError("UFIP source contract unavailable after browser-header retry")
            return expected

        result = fetch_rotterdam_with_retries(
            date(2026, 1, 1),
            date(2026, 9, 8),
            attempts=4,
            delay_seconds=3,
            fetcher=fetcher,
            sleeper=lambda seconds: sleeps.append(seconds),
        )
        self.assertIs(result, expected)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [3, 6])

    def test_retries_still_fail_closed_after_limit(self):
        calls = []

        def fetcher(_start, _end):
            calls.append(1)
            raise RuntimeError("UFIP documented contract unavailable")

        with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
            fetch_rotterdam_with_retries(
                date(2026, 1, 1),
                date(2026, 9, 8),
                attempts=3,
                delay_seconds=0,
                fetcher=fetcher,
                sleeper=lambda _seconds: None,
            )
        self.assertEqual(len(calls), 3)

    def test_success_does_not_sleep_or_refetch(self):
        calls = []
        sleeps = []
        expected = pd.DataFrame({"date": [date(2026, 9, 4)], "rotterdam_eur_l": [1.025]})

        def fetcher(_start, _end):
            calls.append(1)
            return expected

        result = fetch_rotterdam_with_retries(
            date(2026, 1, 1),
            date(2026, 9, 8),
            fetcher=fetcher,
            sleeper=lambda seconds: sleeps.append(seconds),
        )
        self.assertIs(result, expected)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
