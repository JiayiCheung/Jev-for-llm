"""User-selected completion parameters and declarative adjustment rules."""

from copy import deepcopy
from .value_schema import validate_value, validate_schema, validate_action


# These fields belong to the segmented runner, not the parameter controller.
RESERVED_FIELDS = {
    "model",
    "prompt",
    "max_tokens",
    "max_completion_tokens",
    "seed",
    "stream",
    "return_token_ids",
    "add_special_tokens",
    "n",
    "best_of",
}


def validate_parameters(specs):
    if not isinstance(specs, list):
        raise ValueError("parameters.json must contain a list")
    names, targets = set(), set()
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("Each parameter entry must be an object")
        name = spec.get("name")
        target = spec.get("api_name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Parameter names must be unique nonempty strings")
        names.add(name)
        if type(spec.get("enabled")) is not bool:
            raise ValueError(f"{name}: enabled must be boolean")
        if not spec["enabled"]:
            continue
        if spec.get("stage") != "completion":
            raise ValueError(
                f"{name}: this stage needs an adapter; only completion is implemented"
            )
        if not isinstance(target, str) or not target or target in targets:
            raise ValueError(f"{name}: duplicate or invalid API field")
        if target in RESERVED_FIELDS:
            raise ValueError(f"{name}: {target} is managed by the segmented runner")
        targets.add(target)
        validate_schema(spec)
        validate_value(spec["initial"], spec)
        if not isinstance(spec.get("adjustments", {}), dict):
            raise ValueError(f"{name}: adjustments must be an object")
        for trigger, rule in spec.get("adjustments", {}).items():
            if trigger not in ("narrow_sampling", "reduce_repetition"):
                raise ValueError(f"{name}: unknown adjustment trigger {trigger}")
            validate_action(rule, spec)


def initial_parameters(specs):
    return {s["name"]: deepcopy(s["initial"]) for s in specs if s["enabled"]}


def request_parameters(values, specs):
    """Translate experiment names to native SamplingParams keyword arguments."""
    active = {s["name"]: s for s in specs if s["enabled"]}
    if set(values) != set(active):
        raise ValueError("Runtime parameter values do not match the selected list")
    result = {}
    for name, value in values.items():
        validate_value(value, active[name])
        result[active[name]["api_name"]] = deepcopy(value)
    return result


def check_backend_parameters(vllm, specs):
    """Reject absent fields before generation; field presence is not an effect test."""
    values = request_parameters(initial_parameters(specs), specs)
    vllm.validate_parameters(values)
