"""Jev can send a long reasoning back to the start or to an earlier checkpoint."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.config import load_config, validate
from jev_vllm.runner import execute, run_experiment

ROOT = Path(__file__).resolve().parents[1]


class Vllm:
    """One token per round with id 1000 + seed, so another seed gives another token."""

    def __init__(self, stop_seeds=(), max_model_len=10000):
        self.stop_seeds, self.max_model_len, self.requests = (
            set(stop_seeds),
            max_model_len,
            [],
        )

    def validate_parameters(self, values):
        pass

    def tokenize(self, task, enable_thinking):
        return {"tokens": [100, 101], "max_model_len": self.max_model_len}

    def decode(self, tokens):
        return "".join(f"<{t}>" for t in tokens)

    def generate(self, request):
        self.requests.append(request)
        token = 1000 + request["seed"]
        stop = request["seed"] in self.stop_seeds
        return {
            "choices": [
                {
                    "token_ids": [token],
                    "text": f"<{token}>",
                    "finish_reason": "stop" if stop else "length",
                }
            ]
        }


def one_hot(criteria, pick):
    return {k: float(k == pick) for k in criteria}


class Jev:
    def __init__(self, checkpoints=(), verdicts=(), correctness=3):
        self.checkpoints, self.verdicts, self.correctness = (
            list(checkpoints),
            list(verdicts),
            correctness,
        )
        self.requests = []

    def call(self, route, payload):
        self.requests.append(payload)
        questions = payload["questions"]
        if "restart_point" in questions:
            pick = self.checkpoints.pop(0) if self.checkpoints else "continue"
            criteria = questions["restart_point"]["criteria"]
            return {
                "answers": {
                    "restart_point": {
                        "type": "choice",
                        "choice": pick,
                        "probabilities": one_hot(criteria, pick),
                    }
                }
            }
        if "approach" in questions:
            pick = self.verdicts.pop(0) if self.verdicts else "different_approach"
            criteria = questions["approach"]["criteria"]
            return {
                "answers": {
                    "approach": {
                        "type": "choice",
                        "choice": pick,
                        "probabilities": one_hot(criteria, pick),
                    }
                }
            }
        levels = {
            "correctness": self.correctness,
            "relevance": 4,
            "repetition": 0,
            "completeness": 2,
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
                for name in questions
            }
        }


def kinds(jev):
    out = []
    for p in jev.requests:
        q = p["questions"]
        out.append(
            "checkpoint"
            if "restart_point" in q
            else "difference" if "approach" in q else "score"
        )
    return out


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / "config.json")
        self.c["generation"]["chunk_tokens"] = 1
        self.c["experiment"]["mode"] = "fixed"
        self.c["policy"]["restart"].update(
            first_check_round=3, recheck_every=2, max_restarts=2
        )
        self.c["policy"]["restart"]["difference"].update(probe_rounds=2, max_tries=2)
        self.r = {"rounds": [], "jev_calls": 0}

    def run_case(self, vllm, jev):
        execute(self.c, {"id": "t", "prompt": "q"}, 42, vllm, jev, self.r, lambda: None)

    def checkpoint_requests(self, jev):
        return [p for p in jev.requests if "restart_point" in p["questions"]]

    # ---- cadence ---------------------------------------------------------------------------
    def test_first_check_at_the_configured_round_then_every_recheck_rounds(self):
        jev = Jev()
        self.run_case(
            Vllm(stop_seeds={50}), jev
        )  # nine rounds, the model stops in the ninth
        asked = [i for i, k in enumerate(kinds(jev)) if k == "checkpoint"]
        scores_before = [sum(1 for k in kinds(jev)[:i] if k == "score") for i in asked]
        self.assertEqual(scores_before, [3, 5, 7])  # after rounds 3, 5 and 7
        self.assertEqual(self.r["restarts"], [])
        self.assertEqual(self.r["stop_reason"], "model_stop")

    def test_marks_offered_grow_with_each_continue(self):
        jev = Jev()
        self.run_case(Vllm(stop_seeds={50}), jev)
        offered = [
            list(p["questions"]["restart_point"]["criteria"])
            for p in self.checkpoint_requests(jev)
        ]
        self.assertEqual(
            offered,
            [
                ["continue", "back_0"],
                ["continue", "back_0", "back_3"],
                ["continue", "back_0", "back_3", "back_5"],
            ],
        )
        text = self.checkpoint_requests(jev)[1]["questions"]["restart_point"][
            "criteria"
        ]["back_3"]
        self.assertIn("3 tokens", text)
        self.assertIn("correctness was 0.75", text)

    def test_checkpoint_request_carries_the_score_trace(self):
        jev = Jev()
        self.run_case(Vllm(stop_seeds={50}), jev)
        trace = self.checkpoint_requests(jev)[1]["state"]["score_trace"]
        self.assertEqual([t["round"] for t in trace], [1, 2, 3, 4, 5])
        self.assertEqual(trace[0]["correctness"], 0.75)

    # ---- going back to the start -------------------------------------------------------------
    def test_back_to_start_discards_the_text_and_generates_a_fresh_attempt(self):
        jev = Jev(checkpoints=["back_0"], verdicts=["different_approach"])
        vllm = Vllm(stop_seeds={1048})  # epoch 1, step 6
        self.run_case(vllm, jev)
        event = self.r["restarts"][0]
        self.assertEqual(
            (
                event["choice"],
                event["mark_round"],
                event["at_round"],
                event["accepted"],
            ),
            ("back_0", 0, 3, "different"),
        )
        self.assertEqual([t["verdict"] for t in event["tries"]], ["different_approach"])
        self.assertEqual(
            self.r["generated_token_ids"], [2042 + i for i in range(7)]
        )  # only the new attempt remains
        self.assertEqual(self.r["total_generated_tokens"], 3 + 7)
        self.assertEqual(self.r["wasted_tokens"], 3)
        self.assertEqual(self.r["generated_token_count"], 7)
        abandoned = [r["step"] for r in self.r["rounds"] if r.get("abandoned")]
        self.assertEqual(abandoned, [0, 1, 2])
        self.assertTrue(
            all(r.get("epoch") == 1 for r in self.r["rounds"] if not r.get("abandoned"))
        )
        self.assertEqual(
            [r["step"] for r in self.r["rounds"] if r.get("probe")], [0, 1]
        )
        seeds = [q["seed"] for q in vllm.requests]
        self.assertEqual(seeds[:6], [42, 43, 44, 1042, 1043, 1044])

    def test_difference_request_compares_the_abandoned_and_the_new_text(self):
        jev = Jev(checkpoints=["back_0"])
        self.run_case(Vllm(stop_seeds={1048}), jev)
        request = next(p for p in jev.requests if "approach" in p["questions"])
        self.assertEqual(request["state"]["abandoned"], "<1042><1043>")
        self.assertEqual(request["state"]["new"], "<2042><2043>")
        self.assertEqual(
            list(request["questions"]["approach"]["criteria"]),
            ["same_approach", "different_approach"],
        )

    def test_same_approach_is_retried_with_another_seed_until_it_differs(self):
        jev = Jev(
            checkpoints=["back_0"], verdicts=["same_approach", "different_approach"]
        )
        self.run_case(Vllm(stop_seeds={2048}), jev)  # epoch 2, step 6
        event = self.r["restarts"][0]
        self.assertEqual(
            [t["verdict"] for t in event["tries"]],
            ["same_approach", "different_approach"],
        )
        self.assertEqual(event["accepted"], "different")
        self.assertEqual(self.r["generated_token_ids"], [3042 + i for i in range(7)])
        self.assertEqual(self.r["total_generated_tokens"], 3 + 2 + 7)
        self.assertEqual(self.r["wasted_tokens"], 5)

    def test_max_tries_exhausted_keeps_the_last_attempt(self):
        jev = Jev(checkpoints=["back_0"], verdicts=["same_approach", "same_approach"])
        self.run_case(Vllm(stop_seeds={2048}), jev)
        event = self.r["restarts"][0]
        self.assertEqual(len(event["tries"]), 2)
        self.assertEqual(event["accepted"], "max_tries")
        self.assertEqual(self.r["generated_token_ids"][0], 3042)

    # ---- going back to an earlier checkpoint --------------------------------------------------
    def test_back_to_an_earlier_checkpoint_keeps_the_text_before_it(self):
        jev = Jev(checkpoints=["continue", "back_3"])
        self.run_case(Vllm(stop_seeds={1048}), jev)
        event = self.r["restarts"][0]
        self.assertEqual(
            (event["choice"], event["mark_round"], event["at_round"]), ("back_3", 3, 5)
        )
        ids = self.r["generated_token_ids"]
        self.assertEqual(ids[:3], [1042, 1043, 1044])  # the first three rounds survive
        self.assertEqual(ids[3], 2045)  # epoch 1, step 3
        self.assertEqual(self.r["wasted_tokens"], 2)

    # ---- limits of the mechanism --------------------------------------------------------------
    def test_no_more_checkpoints_after_max_restarts(self):
        self.c["policy"]["restart"]["max_restarts"] = 1
        jev = Jev(checkpoints=["back_0", "back_0"])
        self.run_case(Vllm(stop_seeds={1050}), jev)
        self.assertEqual(len(self.r["restarts"]), 1)
        self.assertEqual(len(self.checkpoint_requests(jev)), 1)

    def test_model_stop_during_the_fresh_attempt_ends_the_run(self):
        jev = Jev(checkpoints=["back_0"])
        self.run_case(Vllm(stop_seeds={1042}), jev)
        self.assertEqual(self.r["stop_reason"], "model_stop")
        self.assertEqual(self.r["restarts"][0]["accepted"], "model_stop")
        self.assertNotIn("difference", kinds(jev))

    def test_disabled_and_baseline_never_ask(self):
        self.c["policy"]["restart"]["enabled"] = False
        jev = Jev()
        self.run_case(Vllm(stop_seeds={50}), jev)
        self.assertNotIn("checkpoint", kinds(jev))
        self.r = {"rounds": [], "jev_calls": 0}
        self.c["policy"]["restart"]["enabled"] = True
        self.c["experiment"]["mode"] = "baseline"
        self.run_case(Vllm(stop_seeds={50}), None)
        self.assertEqual(self.r["restarts"], [])

    def test_restart_also_works_in_adaptive_mode_and_resets_the_parameters(self):
        self.c["experiment"]["mode"] = "adaptive"
        jev = Jev(checkpoints=["back_0"])

        original = jev.call

        def pick(name, question):
            """Always raise the temperature when allowed, otherwise keep."""
            if name.startswith("value_"):
                return "v1"
            if name == "direction_temperature" and "increase" in question["criteria"]:
                return "increase"
            return "keep"

        def call(route, payload):
            qs = payload["questions"]
            if (
                qs
                and all(q["type"] == "choice" for q in qs.values())
                and "restart_point" not in qs
                and "approach" not in qs
            ):
                return {
                    "answers": {
                        n: {
                            "type": "choice",
                            "choice": pick(n, q),
                            "probabilities": one_hot(q["criteria"], pick(n, q)),
                        }
                        for n, q in qs.items()
                    }
                }
            return original(route, payload)

        jev.call = call
        self.run_case(Vllm(stop_seeds={1048}), jev)
        fresh = [r for r in self.r["rounds"] if not r.get("abandoned")]
        self.assertEqual(
            fresh[0]["applied_parameters"]["temperature"], 0.6
        )  # back at the initial value
        self.assertGreater(
            max(
                r["applied_parameters"]["temperature"]
                for r in self.r["rounds"]
                if r.get("abandoned")
            ),
            0.6,
        )

    # ---- records ------------------------------------------------------------------------------
    def test_answer_file_leaves_out_abandoned_rounds(self):
        with tempfile.TemporaryDirectory() as folder:
            self.c["paths"]["outputs"] = folder
            jev = Jev(checkpoints=["back_0"])
            run_experiment(
                self.c, {"id": "t", "prompt": "q"}, 42, Vllm(stop_seeds={1048}), jev
            )
            answer = next(Path(folder).glob("*/answer.txt")).read_text(encoding="utf-8")
        self.assertNotIn("<1042>", answer)
        self.assertIn("<2042>", answer)

    def test_restart_settings_are_validated(self):
        for path, value in (
            ("first_check_round", 0),
            ("recheck_every", 0),
            ("max_restarts", -1),
        ):
            old = self.c["policy"]["restart"][path]
            self.c["policy"]["restart"][path] = value
            with self.assertRaises(ValueError, msg=path):
                validate(self.c)
            self.c["policy"]["restart"][path] = old
        for name in ("probe_rounds", "max_tries"):
            self.c["policy"]["restart"]["difference"][name] = 0
            with self.assertRaises(ValueError, msg=name):
                validate(self.c)
            self.c["policy"]["restart"]["difference"][name] = 1


if __name__ == "__main__":
    unittest.main()
