"""Token-bias groups, repetition presets, bad words and the shipped parameter windows."""

import sys
import unittest
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.backend import PythonBackend
from jev_vllm.config import load_config
from jev_vllm.jev_requests import (
    describe_value,
    direction_options,
    direction_request,
    parameter_kind,
    value_candidates,
    value_request,
)
from jev_vllm.parameters import validate_parameters
from jev_vllm.runner import execute

ROOT = Path(__file__).resolve().parents[1]


class ConfigCase(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.spec = {s["name"]: s for s in self.c["parameters"]}
        self.bias = self.spec["logit_bias"]
        self.presets = self.spec["repetition_detection"]


class KindTests(ConfigCase):
    def test_kinds_are_recognised(self):
        self.assertEqual(parameter_kind(self.bias), "mapping")
        self.assertEqual(parameter_kind(self.presets), "preset")
        self.assertEqual(parameter_kind(self.spec["bad_words"]), "collection")

    def test_preset_operations(self):
        self.assertEqual(
            set(direction_options(self.presets, None)), {"keep", "set_preset"}
        )
        current = self.presets["control"]["presets"][0]["value"]
        self.assertEqual(
            set(direction_options(self.presets, current)),
            {"keep", "set_preset", "clear"},
        )
        options = value_candidates(self.presets, current, "set_preset")
        self.assertEqual(len(options), len(self.presets["control"]["presets"]) - 1)
        self.assertNotIn(current, options.values())
        self.assertEqual(
            list(value_candidates(self.presets, current, "clear").values()), [None]
        )

    def test_bad_words_are_added_one_at_a_time(self):
        spec = self.spec["bad_words"]
        words = spec["control"]["candidates"]
        first = value_candidates(spec, None, "add")
        self.assertEqual(
            sorted(map(tuple, first.values())), sorted((w,) for w in words)
        )
        second = value_candidates(spec, [words[0]], "add")
        self.assertTrue(all(v[0] == words[0] and len(v) == 2 for v in second.values()))


class TokenBiasTests(ConfigCase):
    def entries(self, group):
        return [e for e in self.bias["control"]["entries"] if e["group"] == group]

    def test_each_reviewed_entry_is_one_candidate_that_sets_the_whole_group(self):
        options = value_candidates(self.bias, None, "set_entry")
        self.assertEqual(len(options), len(self.bias["control"]["entries"]))
        entry = self.entries("hesitation")[0]
        expected = {str(t): entry["value"] for t in entry["token_ids"]}
        self.assertIn(expected, options.values())

    def test_changing_the_strength_replaces_the_group_instead_of_adding_to_it(self):
        weak, strong = self.entries("hesitation")[0], self.entries("hesitation")[2]
        current = {str(t): weak["value"] for t in weak["token_ids"]}
        options = value_candidates(self.bias, current, "set_entry")
        stronger = {str(t): strong["value"] for t in strong["token_ids"]}
        self.assertIn(stronger, options.values())
        self.assertTrue(all(len(v) >= len(current) for v in options.values()))

    def test_a_group_is_removed_as_a_whole(self):
        entry = self.entries("switching")[1]
        current = {str(t): entry["value"] for t in entry["token_ids"]}
        current["14190"] = -2.0  # a stray single key outside the group
        options = list(value_candidates(self.bias, current, "remove_entry").values())
        self.assertIn({"14190": -2.0}, options)  # the group is gone in one step
        self.assertIn(
            {k: v for k, v in current.items() if k != "14190"}, options
        )  # or the stray key alone

    def test_candidates_are_described_with_readable_labels(self):
        entry = self.entries("hesitation")[0]
        value = {str(t): entry["value"] for t in entry["token_ids"]}
        self.assertEqual(describe_value(self.bias, None, value), entry["label"])
        self.assertEqual(
            describe_value(self.bias, value, None), "Clear every token bias."
        )
        self.assertEqual(
            describe_value(self.bias, value, {}),
            "Remove the bias on the hesitation tokens.",
        )
        self.assertEqual(
            describe_value(self.spec["temperature"], 0.6, 0.7), "Use exact value 0.7"
        )

    def test_value_question_shows_labels_not_token_ids(self):
        scores = {k: {"normalized": 0.5} for k in self.c["jev"]["questions"]}
        _, offered = direction_request(
            "t",
            "g",
            "r",
            0,
            scores,
            self.c["sampling"],
            self.c["parameters"],
            self.c["jev"],
        )
        request, exact, _ = value_request(
            "t",
            "g",
            "r",
            0,
            scores,
            self.c["sampling"],
            {"direction_logit_bias": "set_entry"},
            offered,
            self.c["jev"],
        )
        criteria = request["questions"]["value_logit_bias"]["criteria"]
        self.assertTrue(all("odds of" in text for text in criteria.values()))
        self.assertFalse(any("14190" in text for text in criteria.values()))
        self.assertEqual(len(exact["value_logit_bias"][1]), len(criteria))


class ValidationTests(ConfigCase):
    def bad(self, name, change):
        spec = deepcopy(self.spec[name])
        change(spec["control"])
        with self.assertRaises(ValueError):
            validate_parameters([spec])

    def test_invalid_token_entries_are_rejected(self):
        for change in (
            lambda ctl: ctl["entries"][0].pop("label"),
            lambda ctl: ctl["entries"][0].update(token_ids=[]),
            lambda ctl: ctl["entries"][0].update(token_ids=[-1]),
            lambda ctl: ctl["entries"][0].update(token_ids="14190"),
            lambda ctl: ctl["entries"][0].update(value=1000.0),
        ):
            self.bad("logit_bias", change)

    def test_invalid_presets_are_rejected(self):
        for change in (
            lambda ctl: ctl["presets"].clear(),
            lambda ctl: ctl["presets"][0].update(label=ctl["presets"][1]["label"]),
            lambda ctl: ctl["presets"][0].update(extra=1),
            lambda ctl: ctl["presets"][0]["value"].update(min_count="three"),
            lambda ctl: ctl["presets"][0]["value"].update(unknown=1),
        ):
            self.bad("repetition_detection", change)


class ShippedParametersTests(ConfigCase):
    def test_names_and_native_fields_are_unique(self):
        self.assertEqual(len(self.c["parameters"]), 22)
        for key in ("name", "api_name"):
            self.assertEqual(len({s[key] for s in self.c["parameters"]}), 22)

    def test_numeric_windows_stay_inside_vllm_validity_ranges(self):
        ranges = {
            "temperature": (0, 2),
            "top_p": (0, 1),
            "min_p": (0, 1),
            "frequency_penalty": (-2, 2),
            "presence_penalty": (-2, 2),
            "repetition_penalty": (0, float("inf")),
            "top_k": (0, float("inf")),
        }
        for name, (low, high) in ranges.items():
            window = self.spec[name]["control"]["window"]
            self.assertGreaterEqual(window[0], low, name)
            self.assertLessEqual(window[1], high, name)
        self.assertGreater(self.spec["top_p"]["control"]["window"][0], 0)
        self.assertGreater(
            self.spec["temperature"]["control"]["window"][0], 0
        )  # never greedy

    def test_initial_values_are_the_model_cards_recommended_sampling(self):
        initial = self.c["sampling"]
        self.assertEqual(
            (
                initial["temperature"],
                initial["top_p"],
                initial["top_k"],
                initial["min_p"],
            ),
            (0.6, 0.95, 20, 0.0),
        )

    def test_both_directions_exist_wherever_the_window_allows(self):
        for name in (
            "temperature",
            "top_p",
            "top_k",
            "repetition_penalty",
            "frequency_penalty",
            "presence_penalty",
        ):
            options = direction_options(self.spec[name], self.c["sampling"][name])
            self.assertIn("increase", options, name)
            self.assertIn("decrease", options, name)

    def test_reviewed_bias_groups_cover_three_ideas_with_graded_strengths(self):
        groups = {}
        for entry in self.bias["control"]["entries"]:
            groups.setdefault(entry["group"], []).append(entry["value"])
        self.assertEqual(set(groups), {"hesitation", "switching", "wrap_up"})
        self.assertTrue(all(v < 0 for v in groups["hesitation"] + groups["switching"]))
        self.assertTrue(all(v > 0 for v in groups["wrap_up"]))
        for values in groups.values():
            self.assertEqual(len(values), len(set(values)))
            self.assertGreaterEqual(len(values), 3)

    def test_repetition_presets_are_consistent(self):
        for preset in self.presets["control"]["presets"]:
            value = preset["value"]
            self.assertLessEqual(value["min_pattern_size"], value["max_pattern_size"])
            self.assertGreaterEqual(value["min_count"], 2)


class BackendConversionTests(unittest.TestCase):
    def test_repetition_detection_dict_becomes_the_native_object(self):
        @dataclass
        class RepetitionDetectionParams:
            max_pattern_size: int = 0
            min_pattern_size: int = 0
            min_count: int = 0

        fake = ModuleType("vllm.sampling_params")
        fake.RepetitionDetectionParams = RepetitionDetectionParams
        backend = PythonBackend.__new__(PythonBackend)
        backend.config = {"generation": {"chunk_tokens": 4}}
        backend.fields = {"repetition_detection", "max_tokens"}
        backend.sampling_class = lambda **values: values
        value = {"max_pattern_size": 30, "min_pattern_size": 5, "min_count": 2}
        with patch.dict(sys.modules, {"vllm.sampling_params": fake}):
            result = backend.validate_parameters({"repetition_detection": value})
        self.assertEqual(
            result["repetition_detection"], RepetitionDetectionParams(30, 5, 2)
        )
        self.assertEqual(
            backend.validate_parameters({"repetition_detection": None})[
                "repetition_detection"
            ],
            None,
        )


class RepetitionStopTests(ConfigCase):
    def test_a_repetition_cut_is_a_normal_segment_end_not_a_stop_or_an_error(self):
        reasons = iter(["length", "repetition", "repetition", "length", "stop"])

        class Vllm:
            requests = []

            def validate_parameters(self, values):
                pass

            def tokenize(self, task, enable_thinking):
                return {"tokens": [1, 2], "max_model_len": 1000}

            def decode(self, tokens):
                return "".join(f"<{t}>" for t in tokens)

            def generate(self, request):
                self.requests.append(request)
                n = len(self.requests)
                return {
                    "choices": [
                        {
                            "token_ids": [n],
                            "text": f"<{n}>",
                            "finish_reason": next(reasons),
                        }
                    ]
                }

        class Jev:
            def call(self, route, payload):
                return {
                    "answers": {
                        n: {
                            "type": "score",
                            "score": 2,
                            "probabilities": {str(i): float(i == 2) for i in range(5)},
                        }
                        for n in payload["questions"]
                    }
                }

        self.c["generation"]["chunk_tokens"] = 1
        self.c["experiment"]["mode"] = "fixed"
        self.c["policy"]["restart"]["enabled"] = False
        record = {"rounds": [], "jev_calls": 0}
        execute(
            self.c, {"id": "t", "prompt": "q"}, 42, Vllm(), Jev(), record, lambda: None
        )
        self.assertEqual(
            len(record["rounds"]), 5
        )  # the two repetition cuts did not end the run
        self.assertEqual(record["stop_reason"], "model_stop")


if __name__ == "__main__":
    unittest.main()
