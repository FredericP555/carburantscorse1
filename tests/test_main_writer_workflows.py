from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class MainWriterWorkflowContracts(unittest.TestCase):
    def test_all_c1_main_writers_share_one_concurrency_group(self):
        for name in (
            "update-weekly.yml",
            "update-station-brands.yml",
            "freshness-badge.yml",
        ):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("group: c1-main-writers", text, name)
            self.assertIn("cancel-in-progress: false", text, name)

    def test_all_c1_main_writers_guard_remote_main_before_push(self):
        for name in (
            "update-weekly.yml",
            "update-station-brands.yml",
            "freshness-badge.yml",
        ):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("WRITER_BASE_SHA", text, name)
            self.assertIn("git fetch origin", text, name)
            self.assertIn("origin/${GITHUB_REF_NAME:-main}", text, name)
            self.assertIn("Main advanced while this writer was running", text, name)


if __name__ == "__main__":
    unittest.main()
