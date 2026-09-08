from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "watchdog-weekly.yml"


class FW02C1WorkflowReceiptTests(unittest.TestCase):
    def test_watchdog_validates_receipt_against_current_content(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", text)
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
