import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_results import analyze, classify_ending, grade_answer, summarize_run


def result(mode, answer, *, batch="batch-001", status="completed", change=False):
    initial = {"temperature": 0.6}
    later = {"temperature": 0.8 if change else 0.6}
    rounds = [
        {
            "step": 0,
            "applied_parameters": initial,
            "generation_request": {"prompt": [1, 2], "temperature": 0.6},
            "generation_seconds": 2.0,
            "evaluation_request": {},
            "evaluation_response": {"usage": {"input_tokens": 10, "output_tokens": 2}},
            "evaluation_seconds": 1.0,
            "direction_request": {} if mode == "adaptive" else None,
            "direction_response": {"usage": {"input_tokens": 4, "output_tokens": 1}} if mode == "adaptive" else None,
            "direction_seconds": 0.5 if mode == "adaptive" else None,
            "decision_will_execute": change,
        },
        {
            "step": 1,
            "applied_parameters": later,
            "generation_request": {"prompt": [1, 2, 3], "temperature": later["temperature"]},
            "generation_seconds": 3.0,
            "evaluation_request": {},
            "evaluation_response": {"usage": {"input_tokens": 12, "output_tokens": 3}},
            "evaluation_seconds": 1.5,
        },
    ]
    return {
        "experiment": {"id": batch, "run_id": f"{mode}-{answer}"},
        "status": status,
        "config": {
            "experiment": {"mode": mode, "seeds": [7]},
            "jev": {"api_key": "secret"},
            "parameters": [{"name": "temperature", "api_name": "temperature"}],
        },
        "task": {
            "id": "gsm8k_1",
            "prompt": "What is two plus two?",
            "reference_answer": "4",
            "source": {"dataset": "GSM8K"},
        },
        "seed": 7,
        "rounds": rounds,
        "generated": f"Final answer: {answer}",
        "generated_token_count": 5,
        "jev_calls": 3 if mode == "adaptive" else 2,
        "elapsed_seconds": 10.0 if mode == "adaptive" else 8.0,
    }


class AnalyzeResultsTests(unittest.TestCase):
    def test_numeric_grade_requires_explicit_final_answer(self):
        task = result("fixed", "4")["task"]
        self.assertEqual(grade_answer(task, "Reasoning: 9. Final answer: \\boxed{4}")["grade_status"], "correct")
        self.assertEqual(grade_answer(task, "Final answer: 5")["grade_status"], "incorrect")
        self.assertEqual(grade_answer(task, "Numbers 4 and 5 appear in the work.")["grade_status"], "ungraded")
        self.assertEqual(grade_answer(task, "\\boxed{3}. Final answer: 4")["grade_reason"], "conflicting_explicit_answers")
        self.assertEqual(grade_answer(task, "\\boxed{3}</think>Answer: The result is $4 left.")["grade_status"], "correct")

    def test_run_collects_costs_and_only_executed_changes(self):
        adaptive = summarize_run(result("adaptive", "4", change=True), "a/result.json")
        self.assertEqual(adaptive["executed_changes"], 1)
        self.assertEqual(adaptive["jev_input_tokens"], 26)
        self.assertEqual(adaptive["jev_output_tokens"], 6)
        self.assertEqual(adaptive["generation_seconds"], 5.0)
        self.assertEqual(adaptive["jev_seconds"], 3.0)
        stopped = result("adaptive", "4", change=True)
        stopped["rounds"] = stopped["rounds"][:1]
        self.assertEqual(summarize_run(stopped, "b/result.json")["executed_changes"], 0)

    def test_batch_report_pairs_only_matching_conditions_and_reports_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outputs = root / "outputs"
            reports = root / "reports"
            for name, data in {
                "fixed": result("fixed", "4"),
                "adaptive": result("adaptive", "5", change=True),
                "legacy": result("adaptive", "4", batch=None),
            }.items():
                folder = outputs / name
                folder.mkdir(parents=True)
                (folder / "result.json").write_text(json.dumps(data), encoding="utf-8")
            (outputs / "experiments").mkdir()
            (outputs / "experiments" / "batch-001.json").write_text(json.dumps({
                "planned_runs": 4, "task_ids": ["gsm8k_1", "gsm8k_2"],
                "seeds": [7], "modes": ["fixed", "adaptive"],
            }), encoding="utf-8")
            summary = analyze(outputs, reports, "batch-001")
            self.assertEqual(summary["paired_completed"], 1)
            self.assertEqual(summary["paired_graded"], 1)
            self.assertEqual(summary["fixed_correct"], 1)
            self.assertEqual(summary["adaptive_correct"], 0)
            self.assertEqual(summary["accuracy_delta_pp"], -100.0)
            self.assertEqual(summary["accuracy_resolution_pp"], 100.0)
            self.assertEqual(summary["discordant_pairs"], {"adaptive_only": 0, "fixed_only": 1})
            self.assertEqual(summary["endings"]["fixed"], {"answered": 1})
            self.assertEqual(summary["answered_pairs"], 1)
            self.assertEqual(summary["paired_executed_changes"], 1)
            self.assertEqual(summary["unbatched_runs"], 1)
            self.assertEqual(summary["planned_pairs"], 2)
            self.assertEqual(summary["unobserved_pairs"], 1)
            self.assertEqual(analyze(outputs, reports, "batch-001")["reused_records"], 3)

            duplicate = result("adaptive", "5", change=True)
            duplicate["experiment"]["run_id"] = "second-adaptive"
            folder = outputs / "duplicate"
            folder.mkdir()
            (folder / "result.json").write_text(json.dumps(duplicate), encoding="utf-8")
            summary = analyze(outputs, reports, "batch-001")
            self.assertEqual(summary["paired_completed"], 0)
            self.assertEqual(summary["ambiguous_pairs"], 1)

    def test_ending_separates_answers_from_failed_endings(self):
        self.assertEqual(classify_ending("model_stop", "correct"), "answered")
        self.assertEqual(classify_ending("score_complete", "incorrect"), "answered")
        self.assertEqual(classify_ending("model_stop", "ungraded"), "stopped_no_answer")
        self.assertEqual(classify_ending("token_budget", "ungraded"), "budget_exhausted")
        self.assertEqual(classify_ending("jev_call_budget", "ungraded"), "budget_exhausted")
        self.assertEqual(classify_ending("score_complete", "ungraded"), "no_answer_other")

    def test_mismatch_and_missing_usage_are_not_silent_zeroes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outputs = root / "outputs"
            reports = root / "reports"
            fixed = result("fixed", "4")
            adaptive = result("adaptive", "4")
            adaptive["config"]["generation"] = {"chunk_tokens": 128}
            adaptive["rounds"][0]["evaluation_response"].pop("usage")
            for name, data in (("fixed", fixed), ("adaptive", adaptive)):
                folder = outputs / name
                folder.mkdir(parents=True)
                (folder / "result.json").write_text(json.dumps(data), encoding="utf-8")
            summary = analyze(outputs, reports, "batch-001")
            self.assertEqual(summary["condition_mismatches"], 1)
            self.assertEqual(summary["paired_completed"], 0)
            rows = reports.joinpath("runs.csv").read_text(encoding="utf-8-sig")
            self.assertIn("condition_hash", rows)
            self.assertEqual(summarize_run(adaptive, "adaptive/result.json")["jev_input_tokens"], None)
            self.assertEqual(summarize_run(adaptive, "adaptive/result.json")["jev_usage_missing_calls"], 1)


if __name__ == "__main__":
    unittest.main()
