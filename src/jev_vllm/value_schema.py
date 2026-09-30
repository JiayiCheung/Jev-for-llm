"""Recursive JSON value constraints and typed parameter operations."""

from copy import deepcopy
import math


TYPES = {
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "string": (str,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def kinds(schema):
    value = schema.get("type")
    result = value if isinstance(value, list) else [value]
    if not result or any(not isinstance(k, str) or k not in TYPES for k in result):
        raise ValueError("type must be a supported type or a nonempty type list")
    return result


def equal(left, right):
    """Keep JSON booleans distinct from numbers, including nested values."""
    if type(left) is not type(right):
        return (
            type(left) in (int, float) and type(right) in (int, float) and left == right
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            equal(left[k], right[k]) for k in left
        )
    return left == right


def validate_schema(schema):
    if not isinstance(schema, dict):
        raise ValueError("Value schema must be an object")
    allowed = kinds(schema)
    for key in ("minimum", "maximum"):
        if key in schema and (
            type(schema[key]) not in (int, float) or not math.isfinite(schema[key])
        ):
            raise ValueError(f"Invalid {key}")
    if schema.get("minimum", -math.inf) > schema.get("maximum", math.inf):
        raise ValueError("Reversed bounds")
    if "integer" in allowed and "number" not in allowed:
        if any(
            k in schema and type(schema[k]) is not int for k in ("minimum", "maximum")
        ):
            raise ValueError("Integer bounds must be integers")
    if "items" in schema:
        validate_schema(schema["items"])
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        raise ValueError("properties must be an object")
    for child in props.values():
        validate_schema(child)
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(k, str) for k in required):
        raise ValueError("required must be a string list")
    additional = schema.get("additional_properties", True)
    if isinstance(additional, dict):
        validate_schema(additional)
    elif type(additional) is not bool:
        raise ValueError("additional_properties must be boolean or a schema")
    if "choices" in schema:
        if not isinstance(schema["choices"], list) or not schema["choices"]:
            raise ValueError("choices must be a nonempty list")
        base = {k: v for k, v in schema.items() if k != "choices"}
        for choice in schema["choices"]:
            validate_value(choice, base)


def validate_value(value, schema, path=None):
    path = path or schema.get("name", "value")
    if not any(type(value) in TYPES[k] for k in kinds(schema)):
        raise ValueError(f"{path}: expected {schema['type']}")
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: expected a finite number")
        if (
            not schema.get("minimum", -math.inf)
            <= value
            <= schema.get("maximum", math.inf)
        ):
            raise ValueError(f"{path}: outside bounds")
    if "choices" in schema and not any(equal(value, v) for v in schema["choices"]):
        raise ValueError(f"{path}: value not in choices")
    if isinstance(value, list):
        for i, item in enumerate(value):
            validate_value(
                item, schema.get("items", {"type": list(TYPES)}), f"{path}[{i}]"
            )
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ValueError(f"{path}: JSON object keys must be strings")
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(f"{path}: missing required keys {sorted(missing)}")
        for key, item in value.items():
            child = schema.get("properties", {}).get(key)
            if child is None:
                extra = schema.get("additional_properties", True)
                if extra is False:
                    raise ValueError(f"{path}: unexpected key {key}")
                child = extra if isinstance(extra, dict) else {"type": list(TYPES)}
            validate_value(item, child, f"{path}.{key}")


def validate_action(rule, spec):
    # Preserve existing numeric-delta files while preferring explicit operations.
    if type(rule) in (int, float):
        rule = {"op": "add", "value": rule}
    if not isinstance(rule, dict) or set(rule) != {"op", "value"}:
        raise ValueError("An action must contain exactly op and value")
    op, value = rule["op"], rule["value"]
    allowed = kinds(spec)
    if op == "set":
        validate_value(value, spec)
    elif op == "add":
        if not set(allowed) <= {"number", "integer"}:
            raise ValueError("add requires a non-null numeric parameter")
        if "minimum" not in spec or "maximum" not in spec:
            raise ValueError("add requires minimum and maximum")
        validate_value(value, {"type": "number" if "number" in allowed else "integer"})
    elif op in ("append", "remove"):
        if "array" not in allowed or not isinstance(value, list):
            raise ValueError(f"{op} requires an array parameter and a list of elements")
        validate_value(
            value, {"type": "array", "items": spec.get("items", {"type": list(TYPES)})}
        )
    elif op == "update":
        if "object" not in allowed or not isinstance(value, dict):
            raise ValueError("update requires an object parameter and an object patch")
        patch_schema = {
            k: v for k, v in spec.items() if k not in ("required", "choices")
        }
        validate_value(value, {**patch_schema, "type": "object"})
    else:
        raise ValueError(f"Unknown parameter operation: {op}")
    return rule


def apply_action(current, rule, spec):
    """Apply one operation on a copy and validate the entire resulting value."""
    rule = validate_action(rule, spec)
    op, value = rule["op"], deepcopy(rule["value"])
    result = deepcopy(current)
    if op == "set":
        result = value
    elif op == "add":
        result = max(spec["minimum"], min(spec["maximum"], current + value))
        if "number" not in kinds(spec):
            result = int(result)
        else:
            result = round(result, 6)
    elif op in ("append", "remove"):
        if not isinstance(result, list):
            raise ValueError(
                f"{spec['name']}: {op} requires a current array; use set first"
            )
        if op == "append":
            for item in value:
                if not any(equal(item, existing) for existing in result):
                    result.append(item)
        else:
            result = [
                item
                for item in result
                if not any(equal(item, removed) for removed in value)
            ]
    elif op == "update":
        if not isinstance(result, dict):
            raise ValueError(
                f"{spec['name']}: update requires a current object; use set first"
            )
        result.update(value)  # Shallow merge; use set to replace nested structures.
    validate_value(result, spec)
    return result
