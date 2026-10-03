"""Verify native routing without importing GPU libraries in offline tests."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jev_vllm.backend import PythonBackend
from jev_vllm.config import load_config


class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config((Path(__file__).resolve().parents[1]) / "config.json")
        self.backend = PythonBackend.__new__(PythonBackend)
        self.backend.config = self.config
        self.backend.fields = {"temperature", "seed", "max_tokens", "detokenize"}
        self.backend.sampling_class = lambda **values: values
        self.calls = []

        def generate(prompts, sampling, use_tqdm):
            self.calls.append((prompts, sampling, use_tqdm))
            choice = SimpleNamespace(
                token_ids=[10],
                text="",
                finish_reason="length",
                stop_reason=None,
                cumulative_logprob=-0.2,
                logprobs=[{10: SimpleNamespace(logprob=-0.2, rank=1)}],
            )
            return [SimpleNamespace(outputs=[choice], prompt_logprobs=None)]

        self.backend.engine = SimpleNamespace(generate=generate)

    def test_representative_distinct_native_fields(self):
        specs = self.config["parameters"]
        self.assertEqual(len(specs), 22)
        self.assertEqual(len({s["api_name"] for s in specs}), 22)
        self.assertNotIn("backend", self.config["generation"])
        self.assertNotIn("python", self.config["paths"])
        self.assertNotIn("server", self.config)

    def test_same_engine_and_updated_native_sampling(self):
        engine = self.backend.engine
        first = self.backend.generate({"prompt": [1, 2], "temperature": 0.6})
        second = self.backend.generate({"prompt": [1, 2, 10], "temperature": 0.5})
        self.assertIs(self.backend.engine, engine)
        self.assertEqual(self.calls[1][0], [{"prompt_token_ids": [1, 2, 10]}])
        self.assertEqual(self.calls[1][1]["temperature"], 0.5)
        self.assertEqual(first["choices"][0]["logprobs"][0]["10"]["rank"], 1)
        self.assertEqual(second["choices"][0]["token_ids"], [10])

    def test_invalid_native_field_fails_before_engine_call(self):
        with self.assertRaisesRegex(ValueError, "not exposed"):
            self.backend.generate({"prompt": [1], "invented": True})
        self.assertEqual(self.calls, [])

    def test_uses_actual_remaining_budget(self):
        self.backend.generate({"prompt": [1], "max_tokens": 2})
        self.assertEqual(self.calls[0][1]["max_tokens"], 2)

    def test_logit_bias_json_keys_become_native_integer_ids(self):
        self.backend.fields.add("logit_bias")
        result = self.backend.validate_parameters({"logit_bias": {"42": -2.0}})
        self.assertEqual(result["logit_bias"], {42: -2.0})


if __name__ == "__main__":
    unittest.main()
