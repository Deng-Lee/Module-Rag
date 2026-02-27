from __future__ import annotations

from typing import Any


class SchemaValidationError(ValueError):
    pass


def validate_tool_args(schema: dict[str, Any], args: Any) -> dict[str, Any]:
    """Validate tool args against a minimal JSON Schema subset.

    Supported (D-4/E-4 scope):
    - type=object
    - properties + required
    - additionalProperties (default: True)
    - primitive types: string/integer/number/boolean/object/array

    Returns the (possibly defaulted) args as dict on success.
    """
    if not isinstance(schema, dict):
        raise SchemaValidationError("inputSchema must be an object")

    st = schema.get("type", "object")
    if st != "object":
        raise SchemaValidationError("only type=object schema is supported")

    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise SchemaValidationError("args must be an object")

    props = schema.get("properties") or {}
    if props is not None and not isinstance(props, dict):
        raise SchemaValidationError("properties must be an object")

    required = schema.get("required") or []
    if required is not None and not isinstance(required, list):
        raise SchemaValidationError("required must be an array")

    for k in required:
        if isinstance(k, str) and k not in args:
            raise SchemaValidationError(f"missing required field: {k}")

    additional = schema.get("additionalProperties", True)
    if additional is False and isinstance(props, dict):
        for k in args.keys():
            if k not in props:
                raise SchemaValidationError(f"unexpected field: {k}")

    # Validate known properties (shallow).
    if isinstance(props, dict):
        for key, prop_schema in props.items():
            if key not in args:
                continue
            _validate_value(key, args[key], prop_schema)

    return args


def _validate_value(key: str, value: Any, prop_schema: Any) -> None:
    if not isinstance(prop_schema, dict):
        return
    t = prop_schema.get("type")
    if not t:
        return

    ok = True
    if t == "string":
        ok = isinstance(value, str)
    elif t == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif t == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif t == "boolean":
        ok = isinstance(value, bool)
    elif t == "object":
        ok = isinstance(value, dict)
    elif t == "array":
        ok = isinstance(value, list)
    else:
        # Unknown type: do not reject (forward-compatible).
        ok = True

    if not ok:
        raise SchemaValidationError(f"field {key} must be {t}")
