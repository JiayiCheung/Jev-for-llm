import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.adapters import parse_scores
from jev_vllm.config import load_config, validate
from jev_vllm.policy import Controller

ROOT = Path(__file__).resolve().parents[1]


def scores(correctness=3, relevance=4, repetition=0, completeness=2):
    return {k: {"score": v, "normalized": v / 4} for k, v in locals().copy().items()}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.p = dict(self.c["sampling"])

    def test_config_paths(self):
        self.assertTrue(Path(self.c["paths"]["dataset"]).is_absolute())

    def test_normalized_composite_score_and_repetition_direction(self):
        ctl = Controller(self.c["policy"], self.c["parameters"], mode="fixed")
        best = scores(correctness=4, relevance=4, completeness=4, repetition=0)
        worst = scores(correctness=0, relevance=0, completeness=0, repetition=4)
        self.assertAlmostEqual(ctl.decide(best, self.p, 0)["utility"], 1)
        self.assertAlmostEqual(ctl.decide(worst, self.p, 0)["utility"], 0)
        repeated = scores(correctness=4, relevance=4, completeness=4, repetition=4)
        self.assertAlmostEqual(ctl.decide(repeated, self.p, 0)["utility"], 0.9)
        self.c["policy"]["utility_weights"] = dict.fromkeys(best, 1.0)
        self.assertAlmostEqual(ctl.decide(repeated, self.p, 0)["utility"], 0.75)

    def test_reject_invalid_weights_and_revert_settings(self):
        for weights in (
            dict.fromkeys(self.c["policy"]["utility_weights"], 0),
            {**self.c["policy"]["utility_weights"], "repetition": -0.1},
        ):
            original = self.c["policy"]["utility_weights"]
            self.c["policy"]["utility_weights"] = weights
            with self.assertRaises(ValueError):
                validate(self.c)
            self.c["policy"]["utility_weights"] = original
        for path, value in (
            (("revert", "rule"), "magnitude"),
            (("revert", "consecutive_declines"), 0),
            (("limits", "max_same_direction"), -1),
            (("dormancy", "skip_rounds"), 1.5),
        ):
            section = self.c["policy"][path[0]]
            old = section[path[1]]
            section[path[1]] = value
            with self.assertRaises(ValueError, msg=path):
                validate(self.c)
            section[path[1]] = old

    def revert_controller(self, **revert):
        self.c["policy"]["revert"].update(revert)
        return Controller(self.c["policy"], self.c["parameters"])

    def feed(self, ctl, correctness, params=None, step=0):
        return ctl.decide(scores(correctness=correctness), params or self.p, step)

    def test_revert_after_k_consecutive_declines_restores_best_parameters(self):
        ctl = self.revert_controller(consecutive_declines=3)
        better = {**self.p, "temperature": 0.4}
        self.assertEqual(self.feed(ctl, 3, self.p, 0)["action"], "hold")
        self.assertEqual(
            self.feed(ctl, 4, self.p, 1)["action"], "hold"
        )  # best, params == self.p
        self.assertEqual(self.feed(ctl, 3, better, 2)["action"], "hold")  # decline 1
        self.assertEqual(self.feed(ctl, 2, better, 3)["action"], "hold")  # decline 2
        result = self.feed(ctl, 1, better, 4)  # decline 3
        self.assertEqual(
            (result["action"], result["reason"]), ("rollback", "consecutive_declines")
        )
        self.assertEqual(result["parameters"], self.p)
        # counters restart after a revert
        self.assertEqual(self.feed(ctl, 0, self.p, 5)["action"], "hold")

    def test_a_non_decline_resets_the_count(self):
        ctl = self.revert_controller(consecutive_declines=3)
        better = {**self.p, "temperature": 0.4}
        for step, value in enumerate((4, 3, 2, 3, 2)):
            result = self.feed(ctl, value, better if step else self.p, step)
        self.assertEqual(result["action"], "hold")

    def test_no_revert_when_already_on_best_parameters(self):
        ctl = self.revert_controller(consecutive_declines=2)
        for step, value in enumerate((4, 3, 2, 1)):
            self.assertEqual(self.feed(ctl, value, self.p, step)["action"], "hold")

    def test_revert_can_be_disabled(self):
        ctl = self.revert_controller(consecutive_declines=1, enabled=False)
        better = {**self.p, "temperature": 0.4}
        self.feed(ctl, 4, self.p, 0)
        for step, value in enumerate((3, 2, 1), start=1):
            self.assertEqual(self.feed(ctl, value, better, step)["action"], "hold")

    def test_below_best_rule_counts_rounds_under_the_best(self):
        ctl = self.revert_controller(rule="below_best", consecutive_declines=2)
        better = {**self.p, "temperature": 0.4}
        self.feed(ctl, 4, self.p, 0)
        self.assertEqual(self.feed(ctl, 2, better, 1)["action"], "hold")
        self.assertEqual(
            self.feed(ctl, 3, better, 2)["action"], "rollback"
        )  # up, but still below best

    def test_no_cooldown_every_scored_round_can_ask_for_a_choice(self):
        ctl = Controller(self.c["policy"], self.c["parameters"])
        first = ctl.decide(scores(), self.p, 0)
        ctl.commit(first, self.p, {"temperature": 0.7}, 0)
        self.assertEqual(ctl.decide(scores(), self.p, 1)["reason"], "choice_ready")

    def test_reject_invalid_budget(self):
        self.c["generation"]["chunk_tokens"] = 0

        with self.assertRaises(ValueError):
            validate(self.c)

    def test_reject_nan(self):
        self.c["sampling"]["temperature"] = float("nan")

        with self.assertRaises(ValueError):
            validate(self.c)

    def test_fixed_policy_never_changes(self):
        ctl = Controller(self.c["policy"], self.c["parameters"], mode="fixed")
        self.assertEqual(
            ctl.decide(scores(correctness=0), self.p, 0)["parameters"], self.p
        )

    def test_low_score_needs_choice_before_adjustment(self):
        s = scores(correctness=0)
        self.assertEqual(
            Controller(self.c["policy"], self.c["parameters"]).decide(s, self.p, 0)[
                "reason"
            ],
            "choice_ready",
        )

    def test_bad_score_rejected(self):
        with self.assertRaises((ValueError, KeyError)):
            parse_scores({"answers": {}}, self.c["jev"]["questions"])

    def test_no_fixed_score_trigger_thresholds(self):
        for score_values in (scores(correctness=0), scores(repetition=4), scores()):
            controller = Controller(self.c["policy"], self.c["parameters"])
            self.assertEqual(
                controller.decide(score_values, self.p, 0)["reason"], "choice_ready"
            )

    def test_score_rubric_may_have_two_levels(self):
        self.c["jev"]["questions"]["correctness"]["criteria"] = ["Wrong", "Right"]
        validate(self.c)


if __name__ == "__main__":
    unittest.main()
