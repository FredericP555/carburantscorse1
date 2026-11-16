from __future__ import annotations

from pathlib import Path
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "watchdog-weekly.yml"


class FW02C1WorkflowReceiptTests(unittest.TestCase):
    def test_watchdog_validates_receipt_against_current_content(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        self.assertRegex(text, re.compile(r"^\s*-?\s*uses:\s*actions/checkout@[0-9a-f]{40}(?:\s*(?:#.*)?)?$", re.MULTILINE))
        self.assertIn("python scripts/validate_current_c1_receipt.py", text)
        self.assertIn("--pages-data-file /tmp/c1-pages-data.json", text)
        self.assertNotIn("jq -e --arg tag", text)

    def test_business_run_is_assigned_only_after_current_receipt_validator(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        validator_pos = text.index("python scripts/validate_current_c1_receipt.py")
        assignment_pos = text.index('business_run="$run_id"', validator_pos)
        none_branch_pos = text.index('elif [ -n "$business_run" ]', assignment_pos)
        self.assertLess(validator_pos, assignment_pos)
        self.assertLess(assignment_pos, none_branch_pos)


if __name__ == "__main__":
    unittest.main()
