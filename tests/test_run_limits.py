"""A run has no token, round or request cap: it ends on model stop or a full context window."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.config import load_config
from jev_vllm.runner import execute

ROOT = Path(__file__).resolve().parents[1]


class FakeVllm:
    def __init__(self, max_model_len, stop_at=None):
        self.max_model_len, self.stop_at, self.requests = max_model_len, stop_at, []

    def validate_parameters(self, values):
        pass

    def tokenize(self, task, enable_thinking):
        return {"tokens": [100, 101], "max_model_len": self.max_model_len}

    def decode(self, tokens):
        return "x" * len(tokens)

    def generate(self, request):
        self.requests.append(request)
        stop = self.stop_at is not None and len(self.requests) >= self.stop_at
        return {
            "choices": [
                {
                    "token_ids": [7],
                    "text": "x",
                    "finish_reason": "stop" if stop else "length",
                }
            ]
        }


class FakeJev:
    def __init__(self):
        self.calls = 0

    def call(self, route, payload):
        self.calls += 1
        return {
            "answers": {
                name: {
                    "type": "score",
                    "score": 2,
                    "probabilities": {str(i): float(i == 2) for i in range(5)},
                }
                for name in payload["questions"]
            }
        }


class RunLimitTests(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.c["generation"]["chunk_tokens"] = 1
        self.c["experiment"]["mode"] = "fixed"
        self.c["policy"]["restart"][
            "enabled"
        ] = False  # these tests are about the limits, not restarts
        self.r = {"rounds": [], "jev_calls": 0}

    def run_case(self, vllm, jev):
        execute(self.c, {"id": "t", "prompt": "q"}, 42, vllm, jev, self.r, lambda: None)

    def test_shipped_config_has_no_cap_keys(self):
        self.assertNotIn("total_tokens", self.c["generation"])
        self.assertNotIn("max_rounds", self.c["generation"])
        self.assertNotIn("max_jev_calls", self.c["experiment"])
        self.assertNotIn("stopping", self.c["policy"])

    def test_run_goes_past_the_old_caps_and_ends_when_the_context_is_full(self):
        # the old caps were 32 rounds / 8192 tokens / 96 Jev calls
        vllm, jev = FakeVllm(max_model_len=2 + 150), FakeJev()
        self.run_case(vllm, jev)
        self.assertEqual(len(self.r["rounds"]), 150)
        self.assertEqual(jev.calls, 150)
        self.assertEqual(self.r["stop_reason"], "context_budget")
        self.assertEqual(self.r["generated_token_count"], 150)

    def test_model_stop_still_ends_the_run(self):
        self.run_case(FakeVllm(max_model_len=1000, stop_at=5), FakeJev())
        self.assertEqual(self.r["stop_reason"], "model_stop")
        self.assertEqual(len(self.r["rounds"]), 5)

    def test_baseline_also_runs_to_the_context_limit(self):
        self.c["experiment"]["mode"] = "baseline"
        vllm = FakeVllm(max_model_len=2 + 60)
        self.run_case(vllm, None)
        self.assertEqual(self.r["stop_reason"], "context_budget")
        self.assertEqual(len(vllm.requests), 60)


if __name__ == "__main__":
    unittest.main()
