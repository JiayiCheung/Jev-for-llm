from copy import deepcopy
from .value_schema import apply_action


class Controller:
    def __init__(self, config, parameters, mode="adaptive"):
        self.c, self.mode = config, mode
        self.parameters = parameters
        self.pending = None
        self.last_change = -1000000

    def decide(self, scores, parameters, step):
        current = deepcopy(parameters)
        result = {
            "action": "hold",
            "parameters": current,
            "reason": "no_trigger",
            "stop": False,
        }

        s = {k: v["normalized"] for k, v in scores.items()}
        raw = {k: v["score"] for k, v in scores.items()}
        weights = self.c["utility_weights"]
        favorable = {**s, "repetition": 1 - s["repetition"]}
        utility = (
            4
            * sum(favorable[k] * w for k, w in weights.items())
            / sum(weights.values())
        )
        result["utility"] = utility

        if self.mode == "fixed":
            result["reason"] = "fixed_parameter_control"

            return result

        if self.pending:
            delta = utility - self.pending["utility"]
            result["feedback_delta"] = delta

            if delta < -self.c["rollback"]["score_drop"]:
                result.update(
                    action="rollback",
                    parameters=self.pending["before"],
                    reason="utility_decreased_after_change",
                )
                self.pending = None
                self.last_change = step

                return result

            self.pending = None
            result["feedback"] = "retain_change"

        if (
            self.c["stopping"]["enabled"]
            and raw["completeness"] >= self.c["stopping"]["completeness_min"]
            and raw["correctness"] >= self.c["stopping"]["correctness_min"]
            and raw["relevance"] >= self.c["stopping"]["relevance_min"]
        ):
            result.update(action="stop", stop=True, reason="score_complete")

            return result

        if step - self.last_change <= self.c["cooldown_rounds"]:
            result["reason"] = "cooldown"

            return result

        if (
            raw["correctness"] <= self.c["correctness_max"]
            or raw["relevance"] <= self.c["relevance_max"]
        ):
            result["reason"] = "narrow_sampling"
        elif raw["repetition"] >= self.c["repetition_min"]:
            result["reason"] = "reduce_repetition"

        for spec in self.parameters:
            if not spec["enabled"]:
                continue
            rule = spec.get("adjustments", {}).get(result["reason"])
            if rule is None:
                continue
            name = spec["name"]
            current[name] = apply_action(current[name], rule, spec)

        if current != parameters:
            result["action"] = "adjust"
            self.pending = {"before": deepcopy(parameters), "utility": utility}
            self.last_change = step

        return result
