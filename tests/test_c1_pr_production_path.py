from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "validate-data.yml"


class C1PrProductionPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_pr_validation_uses_real_v2_builder_and_promoter(self):
        self.assertIn("python scripts/build_c1_v2_candidate.py", self.text)
        self.assertIn("python scripts/promote_c1_v2_candidate.py", self.text)
        self.assertNotIn("python scripts/update_data_append.py", self.text)
        self.assertNotIn("python scripts/validate_candidate.py", self.text)

    def test_pr_validation_builds_and_validates_real_shared_bundle(self):
        self.assertIn("python scripts/fetch_ufip.py --output-dir outputs/ufip", self.text)
        self.assertIn("python scripts/export_shared_c2_snapshot.py", self.text)
        self.assertIn("python scripts/validate_shared_c2_snapshot.py", self.text)
        self.assertIn("PrixCarburants_annuel_", self.text)

    def test_production_order_is_preserved(self):
        commands = [
            "python scripts/fetch_ufip.py --output-dir outputs/ufip",
            "python scripts/build_c1_v2_candidate.py",
            "python scripts/promote_c1_v2_candidate.py",
            "python scripts/export_shared_c2_snapshot.py",
            "python scripts/validate_shared_c2_snapshot.py",
        ]
        positions = [self.text.index(command) for command in commands]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
