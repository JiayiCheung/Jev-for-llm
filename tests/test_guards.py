"""Ratchet cap, dormancy, request context, text view and prefix-cache reset."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_runner

from jev_vllm.backend import PythonBackend
from jev_vllm.config import load_config
from jev_vllm.jev_requests import (
    direction_options,
    direction_request,
    evaluation_view,
    objective,
    position,
    score_request,
    value_request,
)
from jev_vllm.policy import Controller

ROOT = Path(__file__).resolve().parents[1]


class ConfigCase(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.specs = {s["name"]: s for s in self.c["parameters"]}
        self.p = dict(self.c["sampling"])


class RatchetAndDormancyTests(ConfigCase):
    def ctl(self):
        return Controller(self.c["policy"], self.c["parameters"])

    def test_same_direction_is_blocked_after_the_cap_and_keep_does_not_break_it(self):
        ctl = self.ctl()
        for step in range(3):
            ctl.note_directions({"repetition_penalty": "increase"}, step)
        self.assertEqual(ctl.blocked(), {"repetition_penalty": ("increase",)})
        ctl.note_directions({"repetition_penalty": "keep"}, 3)
        self.assertEqual(ctl.blocked(), {"repetition_penalty": ("increase",)})
        ctl.note_directions({"repetition_penalty": "decrease"}, 4)
        self.assertEqual(ctl.blocked(), {})

    def test_cap_can_be_switched_off(self):
        self.c["policy"]["limits"]["max_same_direction"] = 0
        ctl = self.ctl()
        for step in range(10):
            ctl.note_directions({"min_p": "increase"}, step)
        self.assertEqual(ctl.blocked(), {})

    def test_blocked_direction_is_not_offered(self):
        spec = self.specs["repetition_penalty"]
        offered = direction_options(spec, 1.1, blocked=("increase",))
        self.assertNotIn("increase", offered)
        self.assertIn("keep", offered)
        self.assertIn(
            "keep", direction_options(spec, 1.1, blocked=("keep",))
        )  # keep is never removed

    def test_dormancy_after_three_keeps_then_wakes_up(self):
        ctl = self.ctl()
        for step in range(3):
            ctl.note_directions({"detokenize": "keep", "temperature": "decrease"}, step)

        def names(step):
            return {s["name"] for s in ctl.active_specs(step)}

        self.assertNotIn("detokenize", names(3))
        self.assertNotIn("detokenize", names(7))
        self.assertIn("detokenize", names(8))  # step 2 + 1 + skip_rounds(5) = 8
        self.assertIn("temperature", names(3))

    def test_a_non_keep_answer_resets_the_keep_streak(self):
        ctl = self.ctl()
        for step, d in enumerate(("keep", "keep", "increase", "keep", "keep")):
            ctl.note_directions({"min_p": d}, step)
        self.assertIn("min_p", {s["name"] for s in ctl.active_specs(5)})


class RequestContextTests(ConfigCase):
    def test_position_reports_window_location_and_steps_left(self):
        top_k = position(self.specs["top_k"], 20)
        self.assertEqual(top_k["steps_left"], {"increase": 36, "decrease": 3})
        self.assertAlmostEqual(top_k["normalized_position"], 0.095)
        rp = position(self.specs["repetition_penalty"], 1.0)
        self.assertEqual(
            (rp["normalized_position"], rp["steps_left"]["decrease"]), (0.333, 10)
        )

    def test_position_is_absent_for_non_numeric_disabled_and_null_values(self):
        self.assertIsNone(position(self.specs["ignore_eos"], False))
        self.assertIsNone(position(self.specs["logprobs"], None))
        self.assertIsNone(position(self.specs["top_k"], 0))  # disabled sentinel

    def test_decision_requests_carry_objective_and_position_but_score_does_not(self):
        scores = {k: {"normalized": 0.5} for k in self.c["jev"]["questions"]}
        goal = objective(self.c["policy"]["utility_weights"])
        direction, offered = direction_request(
            "t",
            "g",
            "r",
            0,
            scores,
            self.p,
            self.c["parameters"],
            self.c["jev"],
            {},
            goal,
        )
        self.assertEqual(
            direction["state"]["objective"]["weights"]["correctness"], 0.45
        )
        instr = direction["questions"]["direction_top_k"]["instructions"]
        self.assertEqual(instr["steps_left"]["decrease"], 3)
        self.assertNotIn(
            "steps_left", direction["questions"]["direction_ignore_eos"]["instructions"]
        )
        value, _, _ = value_request(
            "t",
            "g",
            "r",
            0,
            scores,
            self.p,
            {"direction_temperature": "increase"},
            offered,
            self.c["jev"],
            goal,
        )
        self.assertIn("objective", value["state"])
        self.assertNotIn(
            "objective", score_request("t", "g", "r", 0, self.c["jev"])["state"]
        )
        self.assertEqual(
            set(score_request("t", "g", "r", 0, self.c["jev"])["state"]),
            {"task", "generated", "recent", "step"},
        )

    def test_dormant_and_blocked_parameters_leave_the_question_set(self):
        scores = {k: {"normalized": 0.5} for k in self.c["jev"]["questions"]}
        awake = [s for s in self.c["parameters"] if s["name"] != "detokenize"]
        request, _ = direction_request(
            "t",
            "g",
            "r",
            0,
            scores,
            self.p,
            awake,
            self.c["jev"],
            {"temperature": ("increase",)},
            None,
        )
        self.assertNotIn("direction_detokenize", request["questions"])
        self.assertNotIn(
            "increase", request["questions"]["direction_temperature"]["criteria"]
        )
        self.assertNotIn("objective", request["state"])


class EvaluationViewTests(unittest.TestCase):
    def test_old_segments_are_shortened_recent_ones_kept_and_specials_removed(self):
        segments = ["a" * 500 + "<|im_end|>", "b" * 500, "c" * 500, "d" * 500, "e" * 50]
        view = evaluation_view(segments, keep_full=3, head=10, tail=20)
        self.assertEqual(view.count("[…]"), 2)
        self.assertIn("c" * 500 + "d" * 500 + "e" * 50, view)
        self.assertNotIn("<|im_end|>", view)

    def test_text_from_the_thinking_close_onward_is_never_shortened(self):
        segments = [
            "a" * 500,
            "b" * 100 + "</think>",
            "ANSWER " * 100,
            "x" * 500,
            "y" * 500,
            "z" * 500,
        ]
        view = evaluation_view(segments, keep_full=1, head=5, tail=5)
        self.assertIn("ANSWER " * 100, view)
        self.assertIn("b" * 100 + "</think>", view)
        self.assertEqual(view.count("[…]"), 1)  # only the first segment

    def test_short_input_is_unchanged_apart_from_special_tokens(self):
        self.assertEqual(
            evaluation_view(["<think>\nhi", " there<|im_end|>"]), "<think>\nhi there"
        )


class ResetCacheTests(unittest.TestCase):
    def backend(self, result):
        b = PythonBackend.__new__(PythonBackend)
        b.engine = SimpleNamespace(reset_prefix_cache=lambda: result)
        return b

    def test_success_is_silent_and_failure_is_loud(self):
        self.backend(True).reset_cache()
        with self.assertRaisesRegex(RuntimeError, "prefix cache"):
            self.backend(False).reset_cache()


class RunnerScenarioTests(unittest.TestCase):
    class Vllm(test_runner.FakeVllm):
        def __init__(self):
            super().__init__()
            self.max_model_len = (
                10  # eight rounds of one token after a two-token prompt
            )

    class Jev(test_runner.FakeJev):
        """Score correctness follows `script`; Choice answers always push temperature up."""

        def __init__(self, script):
            super().__init__()
            self.script, self.scored = script, 0

        def call(self, route, payload):
            if all(q["type"] == "choice" for q in payload["questions"].values()):
                self.calls += 1
                answers = {}
                for name, q in payload["questions"].items():
                    pick = (
                        "v1"
                        if name.startswith("value_")
                        else (
                            "increase"
                            if name == "direction_temperature"
                            and "increase" in q["criteria"]
                            else "keep"
                        )
                    )
                    answers[name] = {
                        "type": "choice",
                        "choice": pick,
                        "probabilities": {k: float(k == pick) for k in q["criteria"]},
                    }
                return {"answers": answers}
            self.calls += 1
            value = self.script[min(self.scored, len(self.script) - 1)]
            self.scored += 1
            levels = {
                "correctness": value,
                "relevance": 4,
                "repetition": 0,
                "completeness": 4,
            }
            return {
                "answers": {
                    name: {
                        "type": "score",
                        "score": levels[name],
                        "probabilities": {
                            str(i): float(i == levels[name]) for i in range(5)
                        },
                    }
                    for name in payload["questions"]
                }
            }

    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.c["generation"]["chunk_tokens"] = 1
        self.v = self.Vllm()
        self.r = {"rounds": [], "jev_calls": 0}

    def run_case(self, jev):
        test_runner.execute(
            self.c, {"id": "fake", "prompt": "q"}, 42, self.v, jev, self.r, lambda: None
        )

    def test_three_declines_restore_the_best_parameters_without_asking_jev(self):
        # round 0 is the best; temperature is raised by the fake choices, then utility falls
        jev = self.Jev(script=[4, 3, 2, 1, 1, 1, 1, 1])
        self.run_case(jev)
        rounds = self.r["rounds"]
        rolled = [
            i for i, row in enumerate(rounds) if row["decision"]["action"] == "rollback"
        ]
        self.assertEqual(rolled, [3])
        self.assertNotIn("direction_request", rounds[3])  # no question after a revert
        self.assertEqual(
            rounds[4]["applied_parameters"], rounds[0]["applied_parameters"]
        )
        self.assertEqual(self.r["rounds"][4]["applied_parameters"]["temperature"], 0.6)

    def test_ratchet_cap_stops_a_parameter_being_pushed_forever(self):
        jev = self.Jev(script=[4])  # constant quality: nothing triggers a revert
        self.run_case(jev)
        temps = [row["applied_parameters"]["temperature"] for row in self.r["rounds"]]
        # increase is chosen every time it is offered; it may only move 3 times in a row
        self.assertEqual(len(set(temps)), 4)
        self.assertEqual(temps[3], temps[-1])

    def test_choice_requests_use_the_shortened_view_but_score_requests_do_not(self):
        self.c["jev"]["view"].update(keep_full=1, head=1, tail=1, score=False)
        seen = []
        jev = self.Jev(script=[3])
        original = jev.call
        jev.call = lambda route, payload: (
            seen.append(payload),
            original(route, payload),
        )[1]
        self.v.decode = lambda tokens: "x" * 10 * len(tokens)
        self.v.max_model_len = 5
        self.run_case(jev)
        scores = [p for p in seen if "correctness" in p["questions"]]
        choices = [p for p in seen if "correctness" not in p["questions"]]
        self.assertTrue(all("[…]" not in p["state"]["generated"] for p in scores))
        self.assertTrue(any("[…]" in p["state"]["generated"] for p in choices))
        self.c["jev"]["view"]["score"] = True
        seen.clear()
        self.r = {"rounds": [], "jev_calls": 0}
        self.v = self.Vllm()
        self.v.max_model_len = 5
        self.v.decode = lambda tokens: "x" * 10 * len(tokens)
        self.run_case(jev)
        self.assertTrue(
            any(
                "[…]" in p["state"]["generated"]
                for p in seen
                if "correctness" in p["questions"]
            )
        )


if __name__ == "__main__":
    unittest.main()
