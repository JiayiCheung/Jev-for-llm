import unittest

from scripts.analyze_results import summarize_run


def record():
    def row(step, epoch, temperature, **extra):
        return {
            "step": step,
            "epoch": epoch,
            "applied_parameters": {"temperature": temperature},
            "generation_request": {"prompt": [1], "temperature": temperature},
            "generation_seconds": 1.0,
            **extra,
        }

    return {
        "status": "completed",
        "config": {
            "experiment": {"mode": "fixed"},
            "parameters": [{"name": "temperature"}],
        },
        "task": {"id": "t"},
        "total_generated_tokens": 12,
        "generated_token_count": 7,
        "wasted_tokens": 5,
        "stop_reason": "model_stop",
        "restarts": [{"choice": "back_0"}],
        "rounds": [
            row(0, 0, 0.6, abandoned=True),
            row(1, 0, 0.7, abandoned=True),
            row(
                0, 1, 0.6
            ),  # new attempt: the parameter reset is not an executed change
            row(1, 1, 0.6),
            {
                **row(2, 1, 0.6),
                "checkpoint_request": {},
                "checkpoint_response": {
                    "usage": {"input_tokens": 5, "output_tokens": 1}
                },
                "checkpoint_seconds": 0.5,
            },
        ],
    }


class RestartAnalysisTests(unittest.TestCase):
    def test_cost_counts_every_attempt_and_the_reset_is_not_a_change(self):
        run = summarize_run(record(), "p")
        self.assertEqual(run["generated_tokens"], 12)
        self.assertEqual(run["final_tokens"], 7)
        self.assertEqual(run["wasted_tokens"], 5)
        self.assertEqual(run["restarts"], 1)
        self.assertEqual(
            run["executed_changes"], 1
        )  # 0.6 -> 0.7 inside the first attempt only
        self.assertEqual(run["jev_input_tokens"], 5)
        self.assertEqual(run["jev_seconds"], 0.5)

    def test_records_without_restart_fields_still_work(self):
        old = record()
        for key in ("total_generated_tokens", "wasted_tokens", "restarts"):
            del old[key]
        for r in old["rounds"]:
            r.pop("epoch"), r.pop("abandoned", None)
        run = summarize_run(old, "p")
        self.assertEqual(run["generated_tokens"], 7)
        self.assertEqual(run["wasted_tokens"], 0)
        self.assertEqual(run["restarts"], 0)


if __name__ == "__main__":
    unittest.main()
