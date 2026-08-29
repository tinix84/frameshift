"""Validation against the committed JSON Schemas, with no third-party package.

The harness must read `schemas/` rather than restate it, or the corpus would
drift from the contract it claims to check. This supports exactly the Draft
2020-12 keywords the FrameShift schemas use — `$ref`, `$defs`, `type`,
`properties`, `required`, `additionalProperties`, `items`, `enum`, `const`,
`anyOf`, `minimum`, `minItems`, `minLength`, `maxLength`, `pattern`,
`uniqueItems` — and refuses a schema that uses anything else, so silence never
passes for a check that did not run.

`evals/run.py` and `scripts/validate_repo.py` stay stdlib-only so anyone can
clone and verify with no install; the application's validation library (#1) is
a separate concern and may take a real validator.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"

SUPPORTED = frozenset(
    {
        "$anchor",
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "anyOf",
        "const",
        "default",
        "description",
        "enum",
        "format",
        "items",
        "maxLength",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
        "uniqueItems",
    }
)

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class UnsupportedSchema(ValueError):
    """The schema uses a keyword this validator does not implement."""


def load_schema(name: str) -> dict:
    with (SCHEMAS / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve(ref: str, current: str) -> tuple[dict, str]:
    """Resolve a local (`#/$defs/x`) or cross-file (`other.json#/$defs/x`) ref."""
    filename, _, pointer = ref.partition("#")
    name = filename or current
    node: object = load_schema(name)
    for part in pointer.strip("/").split("/"):
        if part:
            node = node[part]
    return node, name


def _check_keywords(schema: dict, path: str) -> None:
    unsupported = set(schema) - SUPPORTED
    if unsupported:
        raise UnsupportedSchema(f"{path}: unsupported keywords {sorted(unsupported)}")


def validate(value: object, schema: dict, *, current: str, path: str = "$") -> list[str]:
    """Return a list of `path: message` validation errors; empty means valid."""
    _check_keywords(schema, path)
    errors: list[str] = []

    if "$ref" in schema:
        target, name = _resolve(schema["$ref"], current)
        return validate(value, target, current=name, path=path)

    if "anyOf" in schema:
        if not any(not validate(value, option, current=current, path=path) for option in schema["anyOf"]):
            errors.append(f"{path}: matches none of the permitted shapes")
        return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")

    declared = schema.get("type")
    if declared is not None:
        expected = TYPES[declared]
        # JSON has no separate boolean-as-number; a bool is never an integer here.
        if isinstance(value, bool) and declared in ("integer", "number"):
            errors.append(f"{path}: must be {declared}, got boolean")
            return errors
        if not isinstance(value, expected):
            errors.append(f"{path}: must be {declared}, got {type(value).__name__}")
            return errors

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match {schema['pattern']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in value]
            if len(set(encoded)) != len(encoded):
                errors.append(f"{path}: items must be unique")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                errors.extend(validate(item, item_schema, current=current, path=f"{path}[{index}]"))

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}: unexpected property {name!r}")
        for name, item in value.items():
            if name in properties:
                errors.extend(validate(item, properties[name], current=current, path=f"{path}.{name}"))

    return errors


def validate_engine_result(artifact: object) -> list[str]:
    """Validate an engine result against `schemas/engine-result.schema.json`."""
    name = "engine-result.schema.json"
    return validate(artifact, load_schema(name), current=name)
