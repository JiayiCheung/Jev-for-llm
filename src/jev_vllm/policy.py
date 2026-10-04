"""Per-run controller: same-direction cap and dormancy."""

from copy import deepcopy


class Controller:
    """Per-run controller. It records the round and enforces the guards; Jev makes the choices."""

    def __init__(self, config, parameters, mode="adaptive"):
        self.c, self.mode = config, mode
        self.parameters = parameters
        self.moves = {}  # name -> [direction, run length]; "keep" does not break a run
        self.keep_streak = {}  # name -> consecutive keep answers
        self.asleep_until = {}  # name -> first step at which it is asked again

    def decide(self, parameters):
        """Open the decision for one scored round: (action, parameters, reason)."""
        current = deepcopy(parameters)
        result = {
            "action": "hold",
            "parameters": current,
            "reason": "no_trigger",
        }

        if self.mode != "adaptive":
            result["reason"] = "fixed_parameter_control"
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
    def commit(self, result, before, changes):
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
