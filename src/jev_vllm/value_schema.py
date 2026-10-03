"""Recursive JSON value constraints and typed parameter operations."""

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
    """The JSON types a schema allows, as a list."""
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
    """Check that a value schema is well formed."""
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
    """Raise ValueError unless `value` satisfies `schema` (type, bounds, choices, items)."""
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
