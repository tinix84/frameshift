"""The invariants a schema cannot express (#1, ADR-0003, ADR-0012).

`required` and `additionalProperties` see one field at a time, so they cannot
catch an edge pointing at a removed node, an `active_frame_id` naming a frame
that never existed, or an approval bound to a target nobody can find. Every
field is individually valid; the violation lives in the relationship.

The provenance rule is ADR-0012's: a citation carries a type prefix, the prefix
names its namespace, and the namespace decides whether it must resolve. The
registry is the table in `CONTEXT.md` — read from there rather than restated,
so the glossary stays the contract and this stays a reader of it.
"""

from __future__ import annotations

import re
from pathlib import Path

from frameshift.contracts import errors

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "CONTEXT.md"

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION
TARGET_COLLECTIONS = ("statements", "frames", "options", "criteria", "ladder", "symptom_specifications")
REGISTRY_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|[^|]*\|\s*(yes|no)\s*\|", re.MULTILINE)


def provenance_namespaces() -> tuple[frozenset[str], frozenset[str]]:
    """(session-local, external) prefixes, read from the registry in `CONTEXT.md`."""
    table = CONTEXT.read_text(encoding="utf-8").partition(
        "| Prefix | Names | Lives in canonical state |"
    )[2].partition("\n\n")[0]
    local, external = set(), set()
    for prefix, inside in REGISTRY_ROW.findall(table):
        (local if inside == "yes" else external).add(prefix)
    return frozenset(local), frozenset(external)


def _ids(session: dict, collection: str) -> set[str]:
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


def addressable(session: dict) -> set[str]:
    return node_ids(session).union(*(_ids(session, name) for name in TARGET_COLLECTIONS))


def walk_source_ids(value: object, path: str = "$"):
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


def reference_violations(session: dict) -> list[str]:
    """Every reference that must land inside canonical state, and whether it does."""
    violations: list[str] = []
    nodes = node_ids(session)
    frames = _ids(session, "frames")
    reachable = addressable(session)
    local_prefixes, external_prefixes = provenance_namespaces()

    for index, edge in enumerate(session.get("graph", {}).get("edges", [])):
        for end in ("source", "target"):
            if edge.get(end) not in nodes:
                violations.append(
                    f"{INVARIANT_VIOLATION}: dangling reference, $.graph.edges[{index}].{end} "
                    f"names {edge.get(end)!r}, which is not a node in this graph"
                )

    active = session.get("active_frame_id")
    if active is not None and active not in frames:
        violations.append(
            f"{INVARIANT_VIOLATION}: dangling reference, $.active_frame_id names {active!r}, "
            "which is not a frame in this session"
        )

    for index, approval in enumerate(session.get("approvals", [])):
        target = approval.get("target_id")
        if target is not None and target not in reachable:
            violations.append(
                f"{INVARIANT_VIOLATION}: dangling reference, $.approvals[{index}].target_id "
                f"names {target!r}, which is not addressable in this session"
            )

    for source, path in walk_source_ids(session):
        if source.startswith(tuple(external_prefixes)):
            continue
        if not source.startswith(tuple(local_prefixes)):
            violations.append(
                f"{INVARIANT_VIOLATION}: undeclared provenance namespace, {path} cites "
                f"{source!r}, whose prefix is in neither {sorted(local_prefixes)} "
                f"nor {sorted(external_prefixes)}"
            )
        elif source not in reachable:
            violations.append(
                f"{INVARIANT_VIOLATION}: dangling reference, {path} cites {source!r}, "
                "whose namespace is session-local but which is not addressable in this session"
            )

    violations.extend(graph_violations(session.get("graph", {})))
    # #226: intake preserves a request before anyone has classified it, so a
    # draft statement may lack a role. Past draft, a statement is a claim the
    # session acts on, and an unclassified claim cannot be reasoned over.
    for index, statement in enumerate(session.get("statements", [])):
        if (
            isinstance(statement, dict)
            and statement.get("status") != "draft"
            and "primary_role" not in statement
        ):
            violations.append(
                f"{INVARIANT_VIOLATION}: $.statements[{index}] is {statement.get('status')!r} "
                "without a primary_role; only a draft statement may be unclassified"
            )
    # ADR-0024: at most one rung stands at each level of the ladder.
    held: dict = {}
    for index, rung in enumerate(session.get("ladder", [])):
        if not isinstance(rung, dict):
            continue
        level = rung.get("abstraction_level")
        if level in held:
            violations.append(
                f"{INVARIANT_VIOLATION}: $.ladder[{index}] stands at level {level!r}, "
                f"which $.ladder[{held[level]}] already holds"
            )
        else:
            held[level] = index
    violations.extend(symptom_specification_violations(session))
    return violations


def symptom_specification_violations(session: dict) -> list[str]:
    """ADR-0027: a specification's rows, knot and method land in this session."""
    violations: list[str] = []
    statements = {
        item["id"]
        for item in session.get("statements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    nodes = {
        node["id"]
        for node in session.get("graph", {}).get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    for index, spec in enumerate(session.get("symptom_specifications", [])):
        if not isinstance(spec, dict):
            continue
        path = f"$.symptom_specifications[{index}]"
        held: dict = {}
        for row_index, row in enumerate(spec.get("rows", [])):
            if not isinstance(row, dict):
                continue
            dimension = row.get("dimension")
            if dimension in held:
                violations.append(
                    f"{INVARIANT_VIOLATION}: {path}.rows[{row_index}] repeats dimension {dimension!r}, "
                    f"which {path}.rows[{held[dimension]}] already holds"
                )
            else:
                held[dimension] = row_index
            for side in ("is", "is_not"):
                for item_index, item in enumerate(row.get(side, [])):
                    if item not in statements:
                        violations.append(
                            f"{INVARIANT_VIOLATION}: dangling reference, {path}.rows[{row_index}].{side}[{item_index}] "
                            f"names {item!r}, which is not a statement in this session"
                        )
        knot = spec.get("knot_node_id")
        if knot is not None and knot not in nodes:
            violations.append(
                f"{INVARIANT_VIOLATION}: dangling reference, {path}.knot_node_id names {knot!r}, "
                "which is not a node in this graph"
            )
        for item_index, item in enumerate(spec.get("method_source_ids", [])):
            if not (isinstance(item, str) and item.startswith("art_")):
                violations.append(
                    f"{INVARIANT_VIOLATION}: {path}.method_source_ids[{item_index}] names {item!r}, "
                    "which is not a referenced artifact (art_)"
                )
    return violations


def graph_violations(graph: dict) -> list[str]:
    """Apply graph rules that JSON Schema cannot express (ADR-0003)."""
    violations: list[str] = []
    for index, edge in enumerate(graph.get("edges", [])):
        path = f"$.graph.edges[{index}]"
        if edge.get("source") == edge.get("target") and edge.get("feedback_loop") is not True:
            violations.append(
                f"{INVARIANT_VIOLATION}: self-loop at {path} requires feedback_loop: true"
            )
        if edge.get("type") == "causes" and "owner" not in edge:
            violations.append(
                f"{INVARIANT_VIOLATION}: {path}.owner is required for a causes edge"
            )
    return violations


def session_violations(session: dict) -> list[str]:
    """Schema violations and invariant violations, in that order."""
    from .schema import validate_against

    name = "session.v1.schema.json" if session.get("schema_version") == "1.0.0" else "session.v2.schema.json"
    return validate_against(session, name) + reference_violations(session)
