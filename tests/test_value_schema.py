"""Type-aware operations, nested validation, and nonnumeric execution."""

import unittest
from copy import deepcopy

import test_runner

from jev_vllm.parameters import validate_parameters
from jev_vllm.value_schema import validate_schema, validate_value


class ValueSchemaTests(unittest.TestCase):
    def test_nullable_union_and_string_items(self):
        spec = {"type": ["string", "array", "null"], "items": {"type": "string"}}
        validate_schema(spec)
        for value in (None, "END", ["END"]):
            validate_value(value, spec)
        for value in (True, 1, ["END", 2]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_value(value, spec)

    def test_boolean_is_not_a_number_or_numeric_choice(self):
        with self.assertRaises(ValueError):
            validate_value(True, {"type": "number"})
        with self.assertRaises(ValueError):
            validate_value(True, {"type": ["boolean", "integer"], "choices": [1]})

    def test_nested_object_and_required_keys(self):
        spec = {
            "type": "object",
            "required": ["tokens"],
            "additional_properties": False,
            "properties": {
                "tokens": {"type": "array", "items": {"type": "integer", "minimum": 0}}
            },
        }
        validate_schema(spec)
        validate_value({"tokens": [1, 2]}, spec)
        for value in (
            {},
            {"tokens": [True]},
            {"tokens": [-1]},
            {"tokens": [], "extra": 1},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_value(value, spec)

    def test_nested_nonfinite_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_value({"nested": [float("nan")]}, {"type": "object"})


class TypedExecutionTests(unittest.TestCase):
    setUp = test_runner.RunnerTests.setUp
    run_case = test_runner.RunnerTests.run_case

    def test_nullable_integer_enable_then_adjust_by_steps(self):
        from jev_vllm.jev_requests import direction_options, value_candidates

        spec = deepcopy(
            next(s for s in self.c["parameters"] if s["name"] == "logprobs")
        )
        spec.pop("enabled", None)
        spec["control"] = {
            "enable_candidates": [0, 1, 2],
            "window": [0, 20],
            "denominator": 20,
        }
        validate_parameters([spec])
        self.assertEqual(set(direction_options(spec, None)), {"keep", "enable"})
        self.assertEqual(
            value_candidates(spec, None, "enable"), {"v1": 0, "v2": 1, "v3": 2}
        )
        self.assertEqual(
            set(direction_options(spec, 1)),
            {"keep", "increase", "decrease", "disable"},
        )
        self.assertEqual(
            value_candidates(spec, 1, "increase"), {"v1": 2, "v2": 3, "v3": 4}
        )
        self.assertEqual(value_candidates(spec, 1, "decrease"), {"v1": 0})
        self.assertEqual(value_candidates(spec, 1, "disable"), {"v1": None})
        self.assertEqual(value_candidates(spec, 19, "increase"), {"v1": 20})
        self.assertNotIn("decrease", direction_options(spec, 0))

    def test_typed_direction_and_exact_candidates(self):
        from jev_vllm.jev_requests import direction_options, value_candidates

        specs = {s["name"]: s for s in self.c["parameters"]}
        self.assertEqual(len(specs), 22)
        self.assertEqual(
            sum(
                len(direction_options(spec, spec["initial"])) > 1
                for spec in specs.values()
            ),
            20,  # all but stop_token_ids and allowed_token_ids have an operation
        )
        self.assertEqual(
            set(direction_options(specs["ignore_eos"], False)), {"keep", "turn_on"}
        )
        self.assertEqual(
            value_candidates(specs["ignore_eos"], False, "turn_on"), {"v1": True}
        )
        enum_spec = deepcopy(specs["output_kind"])
        enum_spec["control"]["adaptive"] = True
        self.assertEqual(
            value_candidates(enum_spec, "CUMULATIVE", "switch"), {"v1": "FINAL_ONLY"}
        )
        self.assertIn("switch", direction_options(enum_spec, "CUMULATIVE"))
        self.assertIn("disable", direction_options(specs["top_k"], 20))
        self.assertEqual(value_candidates(specs["top_k"], 20, "disable"), {"v1": 0})
        self.assertEqual(set(direction_options(specs["top_k"], 0)), {"keep", "enable"})
        self.assertEqual(
            direction_options(specs["stop_token_ids"], None),
            {"keep": "Keep the current value."},
        )
        self.assertEqual(
            direction_options(specs["allowed_token_ids"], None),
            {"keep": "Keep the current value."},
        )
        self.assertEqual(
            set(direction_options(specs["logit_bias"], None)), {"keep", "set_entry"}
        )
        self.assertEqual(
            set(direction_options(specs["logprobs"], None)), {"keep", "enable"}
        )
        nullable_spec = deepcopy(specs["logprobs"])
        nullable_spec["control"] = {
            "enable_candidates": [1, 3],
            "window": [0, 20],
            "denominator": 20,
        }
        self.assertEqual(
            set(direction_options(nullable_spec, None)), {"keep", "enable"}
        )
        self.assertEqual(
            value_candidates(nullable_spec, None, "enable"), {"v1": 1, "v2": 3}
        )

    def test_reviewed_list_and_mapping_candidates(self):
        from jev_vllm.jev_requests import direction_options, value_candidates

        specs = {s["name"]: deepcopy(s) for s in self.c["parameters"]}
        specs["stop_token_ids"]["control"]["candidates"] = [42]
        specs["allowed_token_ids"]["control"]["candidates"] = [43]
        specs["logit_bias"]["control"]["entries"] = [{"token_id": 42, "value": -2}]
        validate_parameters(list(specs.values()))
        self.assertIn("add", direction_options(specs["stop_token_ids"], None))
        self.assertEqual(
            value_candidates(specs["stop_token_ids"], None, "add"), {"v1": [42]}
        )
        self.assertIn("add", direction_options(specs["allowed_token_ids"], None))
        self.assertEqual(
            value_candidates(specs["allowed_token_ids"], None, "add"), {"v1": [43]}
        )
        self.assertIn("set_entry", direction_options(specs["logit_bias"], None))
        self.assertEqual(
            value_candidates(specs["logit_bias"], None, "set_entry"), {"v1": {"42": -2}}
        )


if __name__ == "__main__":
    unittest.main()
