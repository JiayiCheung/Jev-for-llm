import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.dashboard import discover_experiments, discover_reports


class DashboardDiscoveryTests(unittest.TestCase):
    def test_finds_matching_reports_not_unrelated_newer_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            joined = root / "batch-vs-baseline"
            fixed = root / "batch"
            unrelated = root / "other"
            for path in (joined, fixed, unrelated):
                path.mkdir()
            (joined / "summary.json").write_text(json.dumps({"adaptive_id": "batch"}))
            (joined / "pairs.csv").write_text("task_id,seed\na,1\n")
            (fixed / "pairs.csv").write_text("experiment_id,task_id,seed,status\nbatch,a,1,paired\n")
            (unrelated / "pairs.csv").write_text("experiment_id,task_id,seed,status\nother,a,1,paired\n")
            self.assertEqual(discover_reports(root), (joined, fixed, "batch"))

    def test_no_matching_reports_has_clear_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "paired"):
                discover_reports(Path(folder))

    def test_catalog_keeps_single_and_compare_batches_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifests = root / "manifests"
            manifests.mkdir()
            for batch, modes in (("compare-100", ("fixed", "adaptive")), ("run-10000", ("adaptive",))):
                report = root / batch
                report.mkdir()
                lines = ["experiment_id,task_id,seed,mode,status"]
                lines.extend(f"{batch},task,7,{mode},completed" for mode in modes)
                (report / "runs.csv").write_text("\n".join(lines) + "\n")
            (manifests / "compare-100.json").write_text(json.dumps({"created_utc": "2026-01-01T00:00:00+00:00"}))
            (manifests / "run-10000.json").write_text(json.dumps({"created_utc": "2026-02-01T00:00:00+00:00"}))
            entries = discover_experiments(root, manifests)
            self.assertEqual([entry["id"] for entry in entries], ["compare-100", "run-10000"])
            self.assertEqual({entry["id"]: entry["modes"] for entry in entries},
                             {"compare-100": ["adaptive", "fixed"], "run-10000": ["adaptive"]})

    def test_dashboard_reports_live_outside_manual_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            analysis = root / "analysis"
            reports = root / "dashboard" / "reports"
            legacy = analysis / "auto-old"
            current = reports / "new"
            for path in (legacy, current):
                path.mkdir(parents=True)
                (path / "runs.csv").write_text(
                    "experiment_id,task_id,seed,mode,status\nexample,task,7,adaptive,completed\n"
                )
            entries = discover_experiments(analysis, root / "manifests", reports)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["report"], current)
            self.assertTrue(entries[0]["automatic"])


if __name__ == "__main__":
    unittest.main()
