"""Repair fixes shape and never adds facts (ADR-0006).

Repair is allowed once, and only for shape. That restriction is the whole safety
property: a repair that invents an evidence reference or synthesizes an approval
produces an artifact that is schema-valid and contains a fact nobody asserted.
Schema validation cannot catch it, because the repaired output is valid by
construction — so the subset rule below is what actually holds the line.
"""

from __future__ import annotations

import re

from . import schema

# Keys whose values name something in the domain rather than describe a shape.
# A repair may add structure; it may not add a referent.
IDENTIFIER_KEYS = frozenset({"execution_id", "id", "target_id"})
REFERENCE_KEYS = frozenset({"requested_capabilities", "source_ids"})
# Free-text keys whose values assert something rather than describe a shape: the
# text of a statement, the question a frame poses, what a rationale summary says.
# Rewriting one of these leaves every identifier and reference untouched while
# putting words in the engine's mouth, so the no-new-facts rule covers them too.
ASSERTION_KEYS = frozenset(
    {
        "note",
        "question",
        "rationale_summaries",
        "summary",
        "text",
        "top_outcome",
        "warnings",
    }
)

FRONT_MATTER_ID = re.compile(r"^id:\s*(?P<id>\S+)\s*$", re.MULTILINE)
FRONT_MATTER_VERSION = re.compile(r"^version:\s*(?P<version>\S+)\s*$", re.MULTILINE)


def _collect(value: object, keys: frozenset[str], found: set[str], *, qualify: bool = False) -> set[str]:
    if isinstance(value, dict):
        for name, item in value.items():
            if name in keys:
                prefix = f"{name}: " if qualify else ""
                if isinstance(item, str):
                    found.add(prefix + item)
                elif isinstance(item, list):
                    found.update(prefix + entry for entry in item if isinstance(entry, str))
            _collect(item, keys, found, qualify=qualify)
    elif isinstance(value, list):
        for item in value:
            _collect(item, keys, found, qualify=qualify)
    return found


def referents(artifact: object) -> dict[str, set[str]]:
    """The domain facts an artifact asserts, as four comparable sets.

    Assertions carry their key, so a violation names the field that was
    rewritten rather than only quoting the sentence that replaced it.
    """
    return {
        "identifiers": _collect(artifact, IDENTIFIER_KEYS, set()),
        "references": _collect(artifact, REFERENCE_KEYS, set()),
        "assertions": _collect(artifact, ASSERTION_KEYS, set(), qualify=True),
        "proposal kinds": {
            item.get("kind")
            for item in (artifact.get("proposals", []) if isinstance(artifact, dict) else [])
            if isinstance(item, dict) and isinstance(item.get("kind"), str)
        },
    }


def subset_violations(invalid: object, repaired: object) -> list[str]:
    """The no-new-facts rule: every referent in the repair was already there."""
    before = referents(invalid)
    after = referents(repaired)
    violations: list[str] = []
    for label in before:
        introduced = sorted(after[label] - before[label])
        if introduced:
            violations.append(f"repair introduced {label} absent from the invalid output: {introduced}")
    return violations


def run_repair(invalid: object, candidate: object | None) -> dict:
    """One attempt, for shape only.

    Returns the outcome and the attempt count. The count is part of the result
    rather than an implementation detail, so a future "just retry once more"
    change fails a test instead of passing review.
    """
    errors = schema.validate_engine_result(invalid)
    if not errors:
        return {"outcome": "valid", "attempts": 0, "errors": [], "violations": []}

    if candidate is None:
        return {"outcome": "unrepairable", "attempts": 1, "errors": errors, "violations": []}

    # The repair prompt receives only the validation errors and the invalid
    # output — never prior turns — and it gets exactly one attempt.
    remaining = schema.validate_engine_result(candidate)
    if remaining:
        return {"outcome": "unrepairable", "attempts": 1, "errors": remaining, "violations": []}

    violations = subset_violations(invalid, candidate)
    if violations:
        return {"outcome": "refused", "attempts": 1, "errors": [], "violations": violations}

    return {"outcome": "repaired", "attempts": 1, "errors": [], "violations": []}


def _prompt_errors(case: dict, load_text) -> list[str]:
    """The corpus runs against a pinned prompt version, not whatever is current."""
    pin = case.get("prompt")
    if pin is None:
        return ['case declares no prompt: add "prompt": {"path": ..., "id": ..., "version": ...}']
    try:
        text = load_text(pin["path"])
    except OSError:
        return [f"repair prompt not found: {pin['path']}"]
    errors = []
    for label, pattern in (("id", FRONT_MATTER_ID), ("version", FRONT_MATTER_VERSION)):
        match = pattern.search(text)
        found = match.group(label) if match else None
        if found != pin[label]:
            errors.append(f"repair prompt {label} is {found}, case pins {pin[label]}")
    return errors


def engine_result_repair(case: dict, load) -> list[str]:
    """Run one repair-corpus case and assert outcome, attempts, and the subset rule."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    errors = _prompt_errors(case, lambda relative: (root / relative).read_text(encoding="utf-8"))

    invalid = load(case["invalid"])
    candidate = load(case["repaired"]) if case.get("repaired") else None
    expect = case["expect"]

    result = run_repair(invalid, candidate)

    if result["outcome"] != expect["outcome"]:
        errors.append(f"outcome is {result['outcome']}, case expects {expect['outcome']}")
    if result["attempts"] != expect["attempts"]:
        errors.append(f"{result['attempts']} repair attempts, case expects {expect['attempts']}")

    for fragment in expect.get("errors_naming", []):
        if not any(fragment in item for item in result["errors"]):
            errors.append(f"expected a validation error naming {fragment}, got {result['errors']}")
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in result["violations"]):
            errors.append(f"expected a violation naming {fragment}, got {result['violations']}")

    return errors
