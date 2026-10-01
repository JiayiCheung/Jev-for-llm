from copy import deepcopy


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
        weights = self.c["utility_weights"]
        favorable = {**s, "repetition": 1 - s["repetition"]}
        utility = sum(favorable[k] * w for k, w in weights.items()) / sum(
            weights.values()
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
            and s["completeness"] >= self.c["stopping"]["completeness_min"]
            and s["correctness"] >= self.c["stopping"]["correctness_min"]
            and s["relevance"] >= self.c["stopping"]["relevance_min"]
        ):
            result.update(action="stop", stop=True, reason="score_complete")

            return result

        if step - self.last_change <= self.c["cooldown_rounds"]:
            result["reason"] = "cooldown"

            return result

        result["reason"] = "choice_ready"
        return result

    def commit(self, result, before, changes, step):
        if not changes:
            result["reason"] = "jev_kept_parameters"
            return result
        updated = deepcopy(before)
        updated.update(deepcopy(changes))
        if updated == before:
            result["reason"] = "jev_kept_parameters"
            return result
        result.update(action="adjust", reason="jev_typed_choice", parameters=updated)
        self.pending = {"before": deepcopy(before), "utility": result["utility"]}
        self.last_change = step
        return result
