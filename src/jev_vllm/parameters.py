"""User-selected completion parameters and typed Choice control metadata."""

from copy import deepcopy

from .jev_requests import parameter_kind
from .value_schema import kinds, validate_schema, validate_value

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
    """Check every definition in parameters.json (types, bounds, control data)."""
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
        control = spec.get("control")
        if (
            not isinstance(control, dict)
            or type(control.get("adaptive", True)) is not bool
        ):
            raise ValueError(
                f"{name}: control must be an object with optional boolean adaptive"
            )
        kind = parameter_kind(spec)
        if kind == "unsupported" and control.get("adaptive", True):
            raise ValueError(f"{name}: unsupported adaptive parameter type")
        if kind in ("numeric", "nullable_numeric") and control.get("adaptive", True):
            window = control.get("window")
            denominator = control.get("denominator")
            if (
                not isinstance(window, list)
                or len(window) != 2
                or any(type(x) not in (int, float) for x in window)
                or not spec["minimum"] <= window[0] < window[1] <= spec["maximum"]
                or type(denominator) is not int
                or denominator < 1
            ):
                raise ValueError(
                    f"{name}: invalid numeric control window or denominator"
                )
            if "integer" in (
                spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
            ):
                if round((window[1] - window[0]) / denominator) < 1:
                    raise ValueError(f"{name}: integer step must be at least one")
            if kind == "numeric" and "disabled_value" in control:
                if "enable_value" not in control:
                    raise ValueError(f"{name}: disabled sentinel needs enable_value")
                validate_value(control["disabled_value"], spec)
                validate_value(control["enable_value"], spec)
                if not window[0] <= control["enable_value"] <= window[1]:
                    raise ValueError(f"{name}: enable_value outside control window")
        if kind == "nullable_numeric" and control.get("adaptive", True):
            if "candidates" in control:
                raise ValueError(
                    f"{name}: use enable_candidates for nullable numeric controls"
                )
            candidates = control.get("enable_candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError(f"{name}: enable_candidates must be a nonempty list")
            for item in candidates:
                validate_value(
                    item,
                    {
                        **spec,
                        "type": "integer" if "integer" in kinds(spec) else "number",
                    },
                )
                if not control["window"][0] <= item <= control["window"][1]:
                    raise ValueError(f"{name}: enable candidate outside control window")
        if kind in ("string", "collection"):
            candidates = control.get("candidates", [])
            if not isinstance(candidates, list):
                raise ValueError(f"{name}: candidates must be a list")
            if kind == "string":
                for item in candidates:
                    validate_value(item, {"type": "string"})
            elif kind == "collection":
                for item in candidates:
                    validate_value(item, spec["items"])
        if kind == "mapping":
            entries = control.get("entries", [])
            if not isinstance(entries, list):
                raise ValueError(f"{name}: entries must be a list")
            for item in entries:
                shape = set(item) if isinstance(item, dict) else set()
                if shape == {"token_id", "value"}:
                    ids = [item["token_id"]]
                elif shape == {"label", "group", "token_ids", "value"}:
                    ids = item["token_ids"]
                else:
                    raise ValueError(f"{name}: invalid reviewed token entry")
                if (
                    not isinstance(ids, list)
                    or not ids
                    or any(type(i) is not int or i < 0 for i in ids)
                ):
                    raise ValueError(f"{name}: invalid reviewed token entry")
                validate_value(item["value"], spec["additional_properties"])
        if kind == "preset":
            presets = control["presets"]
            if not isinstance(presets, list) or not presets:
                raise ValueError(f"{name}: presets need at least one entry")
            if any(
                not isinstance(p, dict) or set(p) != {"label", "value"} for p in presets
            ):
                raise ValueError(f"{name}: every preset needs a label and a value")
            labels = [p["label"] for p in presets]
            if any(not isinstance(x, str) or not x for x in labels) or len(
                set(labels)
            ) != len(labels):
                raise ValueError(f"{name}: preset labels must be unique strings")
            for preset in presets:
                validate_value(preset["value"], spec)


def initial_parameters(specs):
    """The initial value of every listed parameter."""
    return {s["name"]: deepcopy(s["initial"]) for s in specs}


def request_parameters(values, specs):
    """Translate experiment names to native SamplingParams keyword arguments."""
    active = {s["name"]: s for s in specs}
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
