"""Per-run controller: utility, revert, same-direction cap and dormancy."""

from copy import deepcopy


class Controller:
    """Per-run controller. Score-derived utility is read-only here: the guards below
    use only the *direction* of change between rounds, never a magnitude threshold."""

    def __init__(self, config, parameters, mode="adaptive"):
        self.c, self.mode = config, mode
        self.parameters = parameters
        self.best_utility, self.best_parameters = None, None
        self.prev_utility, self.declines = None, 0
        self.moves = {}  # name -> [direction, run length]; "keep" does not break a run
        self.keep_streak = {}  # name -> consecutive keep answers
        self.asleep_until = {}  # name -> first step at which it is asked again

    # ---- scores -------------------------------------------------------------
    def utility(self, scores):
        """Weighted quality in [0, 1]; repetition is reversed."""
        s = {k: v["normalized"] for k, v in scores.items()}
        weights = self.c["utility_weights"]
        favorable = {**s, "repetition": 1 - s["repetition"]}
        return sum(favorable[k] * w for k, w in weights.items()) / sum(weights.values())

    def _observe(self, utility, parameters):
        """`utility` was measured on the segment generated with `parameters`."""
        if self.c["revert"]["rule"] == "below_best":
            reference = self.best_utility  # None on the first round
        else:
            reference = self.prev_utility
        self.declines = (
            self.declines + 1 if reference is not None and utility < reference else 0
        )
        if self.best_parameters is None or utility > self.best_utility:
            self.best_utility, self.best_parameters = utility, deepcopy(parameters)
        self.prev_utility = utility

    def _should_revert(self, parameters):
        r = self.c["revert"]
        return (
            r["enabled"]
            and self.declines >= r["consecutive_declines"]
            and parameters != self.best_parameters
        )

    def decide(self, scores, parameters, step):
        """Observe one scored round; return the decision (action, parameters, reason)."""
        current = deepcopy(parameters)
        result = {
            "action": "hold",
            "parameters": current,
            "reason": "no_trigger",
        }
        utility = self.utility(scores)
        result["utility"] = utility

        if self.mode != "adaptive":
            result["reason"] = "fixed_parameter_control"
            return result

        # Track the best utility so far and the run of consecutive declines.
        self._observe(utility, parameters)
        result["declines"] = self.declines

        # Too many declines in a row: go back to the parameters that scored best.
        if self._should_revert(parameters):
            result.update(
                action="rollback",
                parameters=deepcopy(self.best_parameters),
                reason="consecutive_declines",
            )
            self.declines, self.prev_utility = 0, None
            self.moves.clear()
            return result

        result["reason"] = "choice_ready"
        return result

    # ---- guards used when building direction questions ----------------------
    def active_specs(self, step):
        """Parameters that are awake at this step (dormant ones are not asked)."""
        return [
            p for p in self.parameters if self.asleep_until.get(p["name"], 0) <= step
        ]

    def blocked(self):
        """name -> directions that must not be offered (same-direction ratchet cap)."""
        cap = self.c["limits"]["max_same_direction"]
        if not cap:
            return {}
        return {
            name: (direction,)
            for name, (direction, run) in self.moves.items()
            if direction != "keep" and run >= cap
        }

    def note_directions(self, directions, step):
        """directions: parameter name -> chosen operation for the questions asked."""
        dormancy = self.c["dormancy"]
        for name, direction in directions.items():
            if direction == "keep":
                self.keep_streak[name] = self.keep_streak.get(name, 0) + 1
                if (
                    dormancy["keep_streak"]
                    and self.keep_streak[name] >= dormancy["keep_streak"]
                ):
                    self.asleep_until[name] = step + 1 + dormancy["skip_rounds"]
                    self.keep_streak[name] = 0
                continue
            self.keep_streak[name] = 0
            last = self.moves.get(name)
            if last and last[0] == direction:
                last[1] += 1
            else:
                self.moves[name] = [direction, 1]

    # ---- applying a chosen change -------------------------------------------
    def commit(self, result, before, changes, step):
        """Apply the changes Jev chose to the decision, unless they change nothing."""
        if not changes:
            result["reason"] = "jev_kept_parameters"
            return result
        updated = deepcopy(before)
        updated.update(deepcopy(changes))
        if updated == before:
            result["reason"] = "jev_kept_parameters"
            return result
        result.update(action="adjust", reason="jev_typed_choice", parameters=updated)
        return result
