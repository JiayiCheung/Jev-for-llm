import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_run_dashboard import build


class SingleRunDashboardTests(unittest.TestCase):
    def test_builds_single_mode_without_pair_or_jev(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / "report"
            report.mkdir()
            saved = root / "result.json"
            saved.write_text(json.dumps({"config": {"parameters": []}, "task": {"id": "task-1", "prompt": "2 + 2?", "reference_answer": "4"},
                                         "rounds": [], "generated": "4", "stop_reason": "model_stop"}), encoding="utf-8")
            with (report / "runs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["path", "experiment_id", "mode", "task_id", "seed", "status", "grade_status",
                                                            "generated_tokens", "generation_seconds", "jev_seconds", "elapsed_seconds", "jev_calls",
                                                            "jev_input_tokens", "jev_output_tokens", "executed_changes"])
                writer.writeheader()
                writer.writerow({"path": str(saved), "experiment_id": "run-10000", "mode": "baseline", "task_id": "task-1",
                                 "seed": 7, "status": "completed", "grade_status": "correct", "generated_tokens": 8,
                                 "generation_seconds": 2.5, "jev_seconds": 0, "elapsed_seconds": 2.5, "jev_calls": 0,
                                 "jev_input_tokens": 0, "jev_output_tokens": 0, "executed_changes": 0})
            output = root / "dashboard"
            self.assertEqual(build(report, output), ("run-10000", "baseline", 1))
            self.assertTrue((output / "index.html").is_file())
            overview = (output / "data" / "overview.js").read_text(encoding="utf-8")
            self.assertIn('"mode":"baseline"', overview)
            self.assertIn('"seconds":2.5', overview)
            details = json.loads((output / "data" / "detail-index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(details), 1)
            self.assertEqual(next(iter(details.values()))["path"], str(saved))


if __name__ == "__main__":
    unittest.main()
