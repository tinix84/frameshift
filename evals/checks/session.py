"""Canonical state is internally consistent, not merely well-shaped (ADR-0003).

A session can satisfy every schema and still be incoherent: an edge pointing at
a node that was removed, an `active_frame_id` naming a frame that never
existed, an approval bound to a target nobody can find. `additionalProperties`
and `required` cannot catch any of those, because each field is individually
valid — the violation is in the relationship between them.

So this check does two things a schema cannot do alone. It validates the
session against `session.schema.json`, and then it resolves every reference
that must land inside canonical state, naming the JSON path of any that does
not.

Provenance `source_ids` are in scope since ADR-0012, and the rule is the one
that ADR settles: a citation carries a type prefix, and the prefix decides
whether it must resolve. `stmt_001` names a statement in this session and had
better exist; `intake_001` names an intake record the session genuinely cannot
see, and is accepted on its prefix. A prefix nobody declared is a violation, so
the openness cannot become an escape hatch that swallows dangling references.
"""

from __future__ import annotations

from pathlib import Path

from . import errors

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION

# Collections whose members carry an `id` that a reference may name.
TARGET_COLLECTIONS = ("statements", "frames", "options", "criteria")

# The provenance namespaces from ADR-0012. This mirrors the registry table in
# `CONTEXT.md`, which is the contract; `evals/test_session.py` asserts the two
# still agree, so adding a namespace means editing the glossary and not this
# file. A prefix in SESSION_LOCAL must resolve inside canonical state; one in
# EXTERNAL is accepted on its prefix alone.
SESSION_LOCAL_PREFIXES = ("crit_", "frame_", "node_", "opt_", "stmt_")
EXTERNAL_PREFIXES = ("art_", "intake_")
CONTEXT = Path(__file__).resolve().parents[2] / "CONTEXT.md"


def collect_ids(session: dict, collection: str) -> set[str]:
    return {
        item["id"]
        for item in session.get(collection, [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def node_ids(session: dict) -> set[str]:
    return {
        node["id"]
        for node in session.get("graph", {}).get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def reference_violations(session: dict) -> list[str]:
    """Every reference that must land inside canonical state, and where it lands."""
    violations: list[str] = []
    nodes = node_ids(session)
    frames = collect_ids(session, "frames")
    addressable = nodes | set().union(*(collect_ids(session, name) for name in TARGET_COLLECTIONS))

    for index, edge in enumerate(session.get("graph", {}).get("edges", [])):
        for end in ("source", "target"):
            if edge.get(end) not in nodes:
                violations.append(
                    f"{INVARIANT_VIOLATION}: dangling reference, $.graph.edges[{index}].{end} names {edge.get(end)!r}, "
                    "which is not a node in this graph"
                )

    active = session.get("active_frame_id")
    if active is not None and active not in frames:
        violations.append(
            f"{INVARIANT_VIOLATION}: dangling reference, $.active_frame_id names {active!r}, which is not a frame in this session"
        )

    for index, approval in enumerate(session.get("approvals", [])):
        target = approval.get("target_id")
        if target is not None and target not in addressable:
            violations.append(
                f"{INVARIANT_VIOLATION}: dangling reference, $.approvals[{index}].target_id names {target!r}, "
                "which is not addressable in this session"
            )

    violations.extend(provenance_violations(session, addressable))
    return violations


def walk_source_ids(value: object, path: str = "$"):
    """Every `source_ids` entry in the session, with the JSON path it sits at."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_ids" and isinstance(item, list):
                for index, source in enumerate(item):
                    if isinstance(source, str):
                        yield source, f"{path}.source_ids[{index}]"
            else:
                yield from walk_source_ids(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_source_ids(item, f"{path}[{index}]")


def provenance_violations(session: dict, addressable: set[str]) -> list[str]:
    """ADR-0012: the prefix names the namespace, and the namespace decides resolution."""
    violations: list[str] = []
    for source, path in walk_source_ids(session):
        if source.startswith(EXTERNAL_PREFIXES):
            continue
        if not source.startswith(SESSION_LOCAL_PREFIXES):
            violations.append(
                f"{INVARIANT_VIOLATION}: undeclared provenance namespace, {path} cites {source!r}, "
                f"whose prefix is in neither {sorted(SESSION_LOCAL_PREFIXES)} nor {sorted(EXTERNAL_PREFIXES)}"
            )
        elif source not in addressable:
            violations.append(
                f"{INVARIANT_VIOLATION}: dangling reference, {path} cites {source!r}, "
                "whose namespace is session-local but which is not addressable in this session"
            )
    return violations


def session_invariants(case: dict, load) -> list[str]:
    """Validate a session against its schema, then resolve its internal references."""
    from . import schema

    # `at` reaches the session inside a larger document, so the reference
    # checkpoint stays the one golden artifact rather than being copied.
    session = load(case["artifact"])
    for key in case.get("at", []):
        session = session[key]
    for path in case.get("mutate", []):
        _apply(session, path)
    expect = case["expect"]
    errors: list[str] = []

    schema_errors = schema.validate(
        session, schema.load_schema("session.schema.json"), current="session.schema.json"
    )
    violations = schema_errors + reference_violations(session)

    outcome = "invalid" if violations else "valid"
    if outcome != expect["outcome"]:
        errors.append(
            f"session is {outcome}, case expects {expect['outcome']}: "
            f"{violations or 'no violation'}"
        )
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in violations):
            errors.append(f"expected a violation naming {fragment}, got {violations}")
    return errors


def _apply(session: dict, mutation: dict) -> None:
    """Set one JSON path in a copy, so a case can plant exactly one incoherence."""
    container = session
    for key in mutation["path"][:-1]:
        container = container[key]
    container[mutation["path"][-1]] = mutation["value"]
