"""The schemas are themselves checked, not only the artifacts they govern (#113).

`artifact_conformance` walks a schema only along the paths a validated artifact
happens to take. That leaves two ways a constraint can vanish in silence:

- A misspelled keyword — `requred` for `required` — is not a keyword, so nothing
  enforces it. `schema.validate` refuses unsupported keywords, but only at
  positions it visits, and a `$defs` entry no artifact reaches is never visited.
- A `$ref` to a missing file or anchor fails only if some artifact walks into it.

So this check reads each file under `schemas/` as a document in its own right and
visits every subschema position, referenced or not.

Knowing which positions *are* subschemas is the whole difficulty: `properties`
holds schemas keyed by field name, `enum` holds plain values, `const` holds one
value, `required` holds strings. The walker below is keyed on that structure and
refuses any keyword it does not know, which is the same stance `schema.py` takes
toward validation: silence never passes for a check that did not run.
"""

from __future__ import annotations

from . import schema

# Keywords whose value is a subschema, a list of subschemas, or a mapping of
# name to subschema. Everything else in SUPPORTED is a leaf value.
SUBSCHEMA = frozenset({"items", "additionalProperties"})
SUBSCHEMA_LIST = frozenset({"anyOf"})
SUBSCHEMA_MAP = frozenset({"properties", "$defs"})


def schema_files() -> list[str]:
    return sorted(path.name for path in schema.SCHEMAS.glob("*.json"))


def _visit(node: object, name: str, path: str, found: list[str], refs: list[tuple[str, str]]) -> None:
    """Record keyword and reference faults at every subschema position."""
    if not isinstance(node, dict):
        found.append(f"{name} at {path}: expected a subschema object, got {type(node).__name__}")
        return

    unsupported = sorted(set(node) - schema.SUPPORTED)
    if unsupported:
        found.append(f"{name} at {path}: unsupported keywords {unsupported}")

    if "$ref" in node:
        refs.append((node["$ref"], path))

    for keyword in sorted(set(node) & SUBSCHEMA):
        value = node[keyword]
        if isinstance(value, bool):
            continue
        _visit(value, name, f"{path}.{keyword}", found, refs)
    for keyword in sorted(set(node) & SUBSCHEMA_LIST):
        for index, item in enumerate(node[keyword]):
            _visit(item, name, f"{path}.{keyword}[{index}]", found, refs)
    for keyword in sorted(set(node) & SUBSCHEMA_MAP):
        for key in sorted(node[keyword]):
            _visit(node[keyword][key], name, f"{path}.{keyword}.{key}", found, refs)


def file_violations(name: str) -> list[str]:
    """Every keyword and reference fault in one schema file."""
    document = schema.load_schema(name)
    found: list[str] = []
    refs: list[tuple[str, str]] = []
    _visit(document, name, "$", found, refs)

    for ref, path in refs:
        try:
            schema._resolve(ref, name)
        except (OSError, KeyError, TypeError) as exc:
            found.append(f"{name} at {path}: $ref {ref!r} does not resolve ({type(exc).__name__})")
    return found


def schema_wellformedness(case: dict, load) -> list[str]:
    """Walk every schema file in full and report keyword and reference faults."""
    expect = case["expect"]
    errors: list[str] = []

    names = schema_files()
    minimum = expect.get("min_schemas", 1)
    if len(names) < minimum:
        errors.append(f"{len(names)} schema files found, case expects at least {minimum}")

    violations: list[str] = []
    for name in names:
        violations.extend(file_violations(name))

    outcome = "invalid" if violations else "valid"
    if outcome != expect["outcome"]:
        errors.append(f"schemas are {outcome}, case expects {expect['outcome']}: {violations}")
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in violations):
            errors.append(f"expected a violation naming {fragment}, got {violations}")
    return errors
