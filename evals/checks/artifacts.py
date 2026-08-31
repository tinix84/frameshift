"""Every committed artifact validates against the schema that governs it (#1).

`schemas/` is the contract, and the repository ships artifacts that claim to
satisfy it: three capability manifests, a reference checkpoint, sessions, and
engine results. Until now only engine results were validated, so a manifest
could drift from `capability-manifest.schema.json` and every check would still
pass — the schema would be a document rather than a constraint.

The case declares the mapping from artifact to governing schema, so adding an
artifact is a line in a fixture rather than a change here.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import schema

ROOT = Path(__file__).resolve().parents[2]


def governed_artifacts(
    mapping: dict[str, str], deliberately_invalid: dict[str, str] | None = None
) -> list[tuple[str, str]]:
    """Expand each glob to the artifacts it names, paired with its schema.

    Some committed fixtures are invalid on purpose — the repair corpus needs an
    output that no repair can rescue. Those are named one by one with the reason
    they are excluded, so an artifact can never fall out of coverage silently.
    """
    excluded = deliberately_invalid or {}
    found: list[tuple[str, str]] = []
    for pattern, name in sorted(mapping.items()):
        for path in sorted(ROOT.glob(pattern)):
            relative = path.relative_to(ROOT).as_posix()
            if relative not in excluded:
                found.append((relative, name))
    return found


def artifact_conformance(case: dict, load) -> list[str]:
    """Validate every artifact the case governs, naming file and JSON path."""
    mapping = case.get("governs", {})
    expect = case["expect"]
    errors: list[str] = []

    if not mapping:
        return ['case declares no mapping: add "governs": {"<glob>": "<schema>"}']

    excused = case.get("deliberately_invalid", {})
    pairs = governed_artifacts(mapping, excused)
    for relative in excused:
        if not (ROOT / relative).is_file():
            errors.append(f"{relative} is excused as deliberately invalid but does not exist")
    for pattern in mapping:
        if not any(Path(relative).match(pattern) for relative, _ in pairs):
            errors.append(f"no artifact matches {pattern}, so the mapping checks nothing")

    violations: list[str] = []
    for relative, name in pairs:
        try:
            artifact = load(relative)
        except (OSError, json.JSONDecodeError) as exc:
            violations.append(f"{relative} could not be read: {exc}")
            continue
        try:
            found = schema.validate(artifact, schema.load_schema(name), current=name)
        except schema.UnsupportedSchema as exc:
            violations.append(f"{relative} is governed by {name}, which the validator refuses: {exc}")
            continue
        violations.extend(f"{relative} violates {name} at {item}" for item in found)

    minimum = expect.get("min_artifacts", 1)
    if len(pairs) < minimum:
        errors.append(f"{len(pairs)} artifacts governed, case expects at least {minimum}")

    outcome = "invalid" if violations else "valid"
    if outcome != expect["outcome"]:
        errors.append(f"artifacts are {outcome}, case expects {expect['outcome']}: {violations}")
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in violations):
            errors.append(f"expected a violation naming {fragment}, got {violations}")
    return errors
