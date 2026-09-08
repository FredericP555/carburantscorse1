from __future__ import annotations

import unittest

from scripts import validate_current_c1_receipt as current
from scripts import verify_c1_business_success as business


def payload(marker: int = 1) -> bytes:
    return (
        '{"meta":{"last_date":"2026-09-07"},"marker":' + str(marker) + '}'
    ).encode()


def receipt(blob: bytes) -> dict:
    sha = business.sha256_bytes(blob)
    return {
        "status": "business-success",
        "release_tag": "tag",
        "expected_sha256": sha,
        "pages_sha256": sha,
        "release_data_sha256": sha,
    }


class FW02CurrentC1ReceiptTests(unittest.TestCase):
    def test_current_repo_and_pages_match_receipt(self):
        blob = payload()
        current.validate_current_receipt(
            receipt(blob), expected_tag="tag", current_data=blob, pages_data=blob
        )

    def test_old_receipt_rejected_after_repository_change(self):
        old = payload(1)
        new = payload(2)
        with self.assertRaises(ValueError):
            current.validate_current_receipt(
                receipt(old), expected_tag="tag", current_data=new, pages_data=new
            )

    def test_old_receipt_rejected_if_pages_no_longer_match_repo(self):
        blob = payload(1)
        with self.assertRaises(ValueError):
            current.validate_current_receipt(
                receipt(blob), expected_tag="tag", current_data=blob, pages_data=payload(2)
            )

    def test_wrong_release_tag_rejected(self):
        blob = payload()
        with self.assertRaises(ValueError):
            current.validate_current_receipt(
                receipt(blob), expected_tag="other", current_data=blob, pages_data=blob
            )


if __name__ == "__main__":
    unittest.main()
