"""Exercise parameter selection through the actual segmented executor."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import test_runner

from jev_vllm.config import load_config, strip_line_comments, validate
from jev_vllm.parameters import initial_parameters, validate_parameters


class ParameterTests(unittest.TestCase):
    setUp = test_runner.RunnerTests.setUp
    run_case = test_runner.RunnerTests.run_case

    def refresh(self):
        self.c["sampling"] = initial_parameters(self.c["parameters"])
        validate(self.c)

    def test_list_membership_controls_parameter_inclusion_without_enabled(self):
        specs = deepcopy(self.c["parameters"])
        for spec in specs:
            spec.pop("enabled", None)
        validate_parameters(specs)
        values = initial_parameters(specs)
        self.assertIn("temperature", values)
        self.assertEqual(values["logprobs"], None)
        self.assertNotIn("temperature", initial_parameters(specs[1:]))

    def test_new_parameter_changes_without_python_policy_edits(self):
        self.c["parameters"] = [s for s in self.c["parameters"] if s["name"] != "min_p"]
        self.c["parameters"].append(
            {
                "name": "min_p",
                "api_name": "min_p",
                "stage": "completion",
                "type": "number",
                "initial": 0.1,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Alternative probability floor.",
                "control": {"window": [0.0, 1.0], "denominator": 100},
            }
        )
        self.refresh()
        self.run_case()
        self.assertEqual(self.v.requests[0]["min_p"], 0.1)
        self.assertEqual(self.v.requests[1]["min_p"], 0.1)

    def test_removing_parameter_omits_it_from_all_requests(self):
        self.c["parameters"] = self.c["parameters"][1:]
        self.refresh()
        self.run_case()
        self.assertTrue(all("temperature" not in r for r in self.v.requests))

    def test_native_name_maps_to_backend_field(self):
        self.c["parameters"] = [
            s for s in self.c["parameters"] if s["api_name"] != "stop"
        ]
        self.c["parameters"].append(
            {
                "name": "stop_strings",
                "api_name": "stop",
                "stage": "completion",
                "type": "array",
                "initial": ["END"],
                "description": "Stop strings.",
                "items": {"type": "string"},
                "control": {"candidates": []},
            }
        )
        self.refresh()
        self.run_case()
        self.assertEqual(self.v.requests[0]["stop"], ["END"])
        self.assertNotIn("stop_strings", self.v.requests[0])

    def test_integer_candidate_quantizes_without_changing_type(self):
        spec = next(s for s in self.c["parameters"] if s["name"] == "top_k")
        spec.update(minimum=15)
        spec["control"]["window"] = [15, 115]
        spec["control"][
            "denominator"
        ] = 20  # step 5, independent of the shipped parameters.json
        spec["control"].pop("disabled_value")
        spec["control"].pop("enable_value")
        self.refresh()
        from jev_vllm.jev_requests import value_candidates

        options = value_candidates(spec, 20, "decrease")
        self.assertEqual(list(options.values()), [15])
        self.assertIs(type(options["v1"]), int)

    def test_nullable_integer_enable_and_step_reach_later_generations(self):
        class NullableJev(test_runner.FakeJev):
            def call(self, route, payload):
                if not all(
                    q["type"] == "choice" for q in payload["questions"].values()
                ):
                    return super().call(route, payload)
                self.calls += 1
                answers = {}
                for name, question in payload["questions"].items():
                    if name == "direction_logprobs":
                        current = payload["state"]["current_parameters"]["logprobs"]
                        chosen = "enable" if current is None else "increase"
                    elif name == "value_logprobs":
                        current = payload["state"]["current_parameters"]["logprobs"]
                        chosen = "v2" if current is None else "v1"
                    else:
                        chosen = "keep"
                    answers[name] = {
                        "type": "choice",
                        "choice": chosen,
                        "probabilities": {
                            key: float(key == chosen) for key in question["criteria"]
                        },
                    }
                return {"answers": answers}

        self.j = NullableJev()
        self.v.max_model_len = 7  # five rounds
        self.run_case()
        self.assertEqual(
            [request["logprobs"] for request in self.v.requests], [None, 1, 2, 3, 4]
        )

    def test_missing_backend_field_fails_before_generation_or_jev(self):
        self.c["parameters"][0]["api_name"] = "not_a_real_field"
        self.refresh()
        with self.assertRaisesRegex(ValueError, "not exposed"):
            self.run_case()
        self.assertEqual(self.v.requests, [])
        self.assertEqual(self.j.calls, 0)

    def test_invalid_definitions(self):
        original = self.c["parameters"][0]
        for changes in (
            {"stage": "loading"},
            {"api_name": "prompt"},
            {"initial": True},
            {"minimum": 5},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_parameters([{**original, **changes}])
        with self.assertRaises(ValueError):
            validate_parameters([original, original])

    def test_external_list_resolves_relative_to_config(self):
        root = Path(__file__).resolve().parents[1]
        raw = json.loads(strip_line_comments((root / "config.json").read_text()))
        raw["jev"]["questions_file"] = str(root / "jev_questions.json")
        raw["parameters_file"] = "selection.json"
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "selection.json").write_text("# No overrides\n[]")
            (base / "config.json").write_text(json.dumps(raw))
            loaded = load_config(base / "config.json")
            self.assertEqual(loaded["sampling"], {})
            self.assertEqual(loaded["parameters_file"], str(base / "selection.json"))


if __name__ == "__main__":
    unittest.main()
