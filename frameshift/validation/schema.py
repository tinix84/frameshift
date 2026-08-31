"""The application's schema validator (#1, ADR-0006).

Like the encoder in `frameshift.persistence`, this is deliberately a second
implementation. `evals/checks/schema.py` is the harness's reference and says so:
*"the application's validation library (#1) is a separate concern."* The
application cannot import the harness — the harness is test code — and two
validators that agree on every committed artifact are worth more than one
shared by both.

They are structured differently on purpose. The reference walks a schema with an
inline chain of `if` clauses; this dispatches one function per keyword. Two
implementations that agree because they are the same code prove nothing, so the
conformance case compares their *violations*, string for string, on every
committed artifact and on planted faults.

The keyword discipline is #117's, and it is the reason that bug cannot recur
here: every supported keyword is either ENFORCED, meaning some function below
applies it, or an ANNOTATION carrying no constraint. A keyword that is neither
is refused rather than silently ignored, and a test asserts the two sets
partition SUPPORTED and that every ENFORCED keyword has a handler.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"

# Keywords that constrain something. Each has an entry in `_KEYWORDS` below,
# except the four the walker handles structurally: `$ref`, `$defs`, `anyOf`,
# and `properties`/`additionalProperties`, which recurse rather than compare.
ENFORCED = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "enum",
        "items",
        "maxLength",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "properties",
        "required",
        "type",
        "uniqueItems",
    }
)
# Keywords that carry no constraint. Listing them is what stops one being
# mistaken for a check that runs.
ANNOTATIONS = frozenset(
    {"$anchor", "$id", "$schema", "default", "description", "format", "title"}
)
SUPPORTED = ENFORCED | ANNOTATIONS

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
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _resolve(ref: str, current: str) -> tuple[dict, str]:
    filename, _, pointer = ref.partition("#")
    name = filename or current
    node: object = load_schema(name)
    for part in pointer.strip("/").split("/"):
        if part:
            node = node[part]
    return node, name


def _check_type(value, schema, path, current):
    declared = schema["type"]
    if isinstance(value, bool) and declared in ("integer", "number"):
        return [f"{path}: must be {declared}, got boolean"]
    if not isinstance(value, TYPES[declared]):
        return [f"{path}: must be {declared}, got {type(value).__name__}"]
    return []


def _check_const(value, schema, path, current):
    if value != schema["const"]:
        return [f"{path}: must be {schema['const']!r}, got {value!r}"]
    return []


def _check_enum(value, schema, path, current):
    if value not in schema["enum"]:
        return [f"{path}: {value!r} is not one of {schema['enum']}"]
    return []


def _check_min_length(value, schema, path, current):
    if isinstance(value, str) and len(value) < schema["minLength"]:
        return [f"{path}: shorter than {schema['minLength']}"]
    return []


def _check_max_length(value, schema, path, current):
    if isinstance(value, str) and len(value) > schema["maxLength"]:
        return [f"{path}: longer than {schema['maxLength']}"]
    return []


def _check_pattern(value, schema, path, current):
    if isinstance(value, str) and not re.search(schema["pattern"], value):
        return [f"{path}: does not match {schema['pattern']}"]
    return []


def _check_minimum(value, schema, path, current):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema["minimum"]:
            return [f"{path}: below minimum {schema['minimum']}"]
    return []


def _check_min_items(value, schema, path, current):
    if isinstance(value, list) and len(value) < schema["minItems"]:
        return [f"{path}: fewer than {schema['minItems']} items"]
    return []


def _check_unique_items(value, schema, path, current):
    if isinstance(value, list) and schema["uniqueItems"]:
        encoded = [json.dumps(item, sort_keys=True) for item in value]
        if len(set(encoded)) != len(encoded):
            return [f"{path}: items must be unique"]
    return []


def _check_required(value, schema, path, current):
    if not isinstance(value, dict):
        return []
    return [
        f"{path}: missing required property {name!r}"
        for name in schema["required"]
        if name not in value
    ]


def _check_items(value, schema, path, current):
    if not isinstance(value, list):
        return []
    found: list[str] = []
    for index, item in enumerate(value):
        found.extend(validate(item, schema["items"], current=current, path=f"{path}[{index}]"))
    return found


# One function per comparing keyword. `$ref`, `anyOf`, `properties`, `$defs`,
# and `additionalProperties` recurse and are handled in `validate`.
_KEYWORDS = {
    "const": _check_const,
    "enum": _check_enum,
    "items": _check_items,
    "maxLength": _check_max_length,
    "minItems": _check_min_items,
    "minLength": _check_min_length,
    "minimum": _check_minimum,
    "pattern": _check_pattern,
    "required": _check_required,
    "type": _check_type,
    "uniqueItems": _check_unique_items,
}


def validate(value: object, schema: dict, *, current: str, path: str = "$") -> list[str]:
    """Return `path: message` violations. An empty list means the value is valid."""
    unsupported = sorted(set(schema) - SUPPORTED)
    if unsupported:
        raise UnsupportedSchema(f"{path}: unsupported keywords {unsupported}")

    if "$ref" in schema:
        target, name = _resolve(schema["$ref"], current)
        return validate(value, target, current=name, path=path)

    if "anyOf" in schema:
        if any(not validate(value, option, current=current, path=path) for option in schema["anyOf"]):
            return []
        return [f"{path}: matches none of the permitted shapes"]

    violations: list[str] = []
    # `type` first: every other keyword assumes the value is the shape it claims.
    if "type" in schema:
        mismatch = _check_type(value, schema, path, current)
        if mismatch:
            return mismatch

    for keyword in sorted(set(schema) & set(_KEYWORDS)):
        if keyword == "type":
            continue
        violations.extend(_KEYWORDS[keyword](value, schema, path, current))

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties")
        for name, item in sorted(value.items()):
            if name in properties:
                violations.extend(
                    validate(item, properties[name], current=current, path=f"{path}.{name}")
                )
            elif additional is False:
                violations.append(f"{path}: unexpected property {name!r}")
            elif isinstance(additional, dict):
                violations.extend(
                    validate(item, additional, current=current, path=f"{path}.{name}")
                )

    return violations


def validate_against(artifact: object, schema_name: str) -> list[str]:
    """Validate an artifact against a schema named in `schemas/`."""
    return validate(artifact, load_schema(schema_name), current=schema_name)
