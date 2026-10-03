import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.adapters import choice_response, parse_scores, score_response
from jev_vllm.config import load_config
from jev_vllm.jev_requests import parse_choices
from jev_vllm.runner import execute, run_experiment


class FakeVllm:
    def __init__(self, stop=False):
        self.requests = []
        self.stop = stop
        self.max_model_len = 5  # prompt of 2 + 3 generated tokens: three rounds

    def validate_parameters(self, values):
        names = {
            s["api_name"]
            for s in load_config((Path(__file__).resolve().parents[1]) / "config.json")[
                "parameters"
            ]
        }
        if set(values) - names - {"seed", "max_tokens", "min_p", "stop"}:
            raise ValueError("Parameter not exposed")

    def tokenize(self, task, enable_thinking):
        return {"tokens": [100, 101], "max_model_len": self.max_model_len}

    def decode(self, tokens):
        return "x" * len(tokens)

    def generate(self, payload):
        self.requests.append(payload)

        return {
            "choices": [
                {
                    "token_ids": [10 + len(self.requests)],
                    "text": "x",
                    "finish_reason": "stop" if self.stop else "length",
                }
            ]
        }


class FakeJev:
    def __init__(self):
        self.calls = 0

    def call(self, route, payload):
        self.calls += 1
        if all(q["type"] == "choice" for q in payload["questions"].values()):
            return {
                "answers": {
                    name: {
                        "type": "choice",
                        "choice": (
                            "increase"
                            if name == "direction_temperature"
                            else "v1" if name.startswith("value_") else "keep"
                        ),
                        "probabilities": {
                            key: float(
                                key
                                == (
                                    "increase"
                                    if name == "direction_temperature"
                                    else "v1" if name.startswith("value_") else "keep"
                                )
                            )
                            for key in payload["questions"][name]["criteria"]
                        },
                    }
                    for name in payload["questions"]
                }
            }
        return {
            "answers": {
                name: {
                    "type": "score",
                    "score": value,
                    "probabilities": {str(i): float(i == value) for i in range(5)},
                }
                for name, value in zip(payload["questions"], [0, 4, 0, 2])
            }
        }


class RunnerTests(unittest.TestCase):
    def test_unused_answer_metadata_is_not_recorded(self):
        raw = {
            "answers": {
                "example": {
                    "type": "score",
                    "score": 1,
                    "probabilities": {"0": 0, "1": 1},
                    "unused_metadata": 0,
                }
            }
        }
        cleaned = score_response(raw)
        self.assertNotIn("unused_metadata", cleaned["answers"]["example"])
        self.assertIn("unused_metadata", raw["answers"]["example"])
        self.assertEqual(cleaned["answers"]["example"]["score"], 1)

    def test_choice_validation_and_confidence_exclusion(self):
        questions = {
            "direction_temperature": {"criteria": {"keep": "Hold", "increase": "Raise"}}
        }
        raw = {
            "answers": {
                "direction_temperature": {
                    "type": "choice",
                    "choice": "increase",
                    "confidence": 0.7,
                    "probabilities": {"keep": 0.25, "increase": 0.75},
                }
            }
        }
        self.assertEqual(
            parse_choices(raw, questions), {"direction_temperature": "increase"}
        )
        self.assertNotIn(
            "confidence", choice_response(raw)["answers"]["direction_temperature"]
        )
        raw["answers"]["direction_temperature"]["choice"] = "invented"
        with self.assertRaises(ValueError):
            parse_choices(raw, questions)

    def setUp(self):
        self.c = load_config((Path(__file__).resolve().parents[1]) / "config.json")
        self.c["generation"]["chunk_tokens"] = 1
        self.r = {"rounds": [], "jev_calls": 0}
        self.v, self.j = FakeVllm(), FakeJev()

    def run_case(self):
        execute(
            self.c,
            {"id": "fake", "prompt": "Test question"},
            42,
            self.v,
            self.j,
            self.r,
            lambda: None,
        )

    def test_continuation_and_actual_adjustment(self):
        self.run_case()
        self.assertEqual(self.v.requests[1]["prompt"], [100, 101, 11])
        self.assertEqual(self.v.requests[1]["temperature"], 0.7)
        self.assertEqual(self.r["rounds"][1]["applied_parameters"]["temperature"], 0.7)
        self.assertIn("direction_request", self.r["rounds"][0])
        self.assertIn("value_request", self.r["rounds"][0])
        self.assertEqual(
            self.r["rounds"][0]["direction_request"]["state"]["scores"]["correctness"],
            0,
        )
        self.assertFalse(self.r["rounds"][-1]["decision_will_execute"])

    def test_answer_file_records_every_cumulative_round(self):
        self.c["experiment"]["mode"] = "fixed"
        with tempfile.TemporaryDirectory() as folder:
            self.c["paths"]["outputs"] = folder
            result = run_experiment(
                self.c,
                {"id": "fake", "prompt": "Test question"},
                42,
                self.v,
                self.j,
            )
            answer = next(Path(folder).glob("*/answer.txt")).read_text(encoding="utf-8")
        self.assertEqual(len(result["rounds"]), 3)
        self.assertIn("Round 1", answer)
        self.assertIn("Round 2", answer)
        self.assertIn("Round 3", answer)
        self.assertEqual(answer.count("=== Round"), 3)
        self.assertEqual(
            [part.strip().splitlines()[-1] for part in answer.split("=== Round")[1:]],
            ["x", "xx", "xxx"],
        )

    def test_fixed_control(self):
        self.c["experiment"]["mode"] = "fixed"
        self.run_case()
        self.assertEqual([x["temperature"] for x in self.v.requests], [0.6] * 3)

    def test_model_stop(self):
        self.v.stop = True
        self.run_case()
        self.assertEqual(self.r["stop_reason"], "model_stop")
        self.assertEqual(len(self.v.requests), 1)

    def test_raw_evaluation_preserved_on_validation_error(self):
        self.j.call = lambda *args: {"answers": {}}

        with self.assertRaises(KeyError):
            self.run_case()

        self.assertEqual(self.r["rounds"][0]["evaluation_response"], {"answers": {}})

    def test_real_score_schema(self):
        raw = FakeJev().call("", {"questions": self.c["jev"]["questions"]})
        self.assertEqual(
            parse_scores(raw, self.c["jev"]["questions"])["relevance"]["normalized"], 1
        )


if __name__ == "__main__":
    unittest.main()
