"""Graph schema and cross-field invariants from ADR-0003."""

from __future__ import annotations

from . import errors, schema


def graph_violations(graph: dict, *, path_prefix: str = "$.edges") -> list[str]:
    violations: list[str] = []
    for index, edge in enumerate(graph.get("edges", [])):
        path = f"{path_prefix}[{index}]"
        if edge.get("source") == edge.get("target") and edge.get("feedback_loop") is not True:
            violations.append(
                f"{errors.INVARIANT_VIOLATION}: self-loop at {path} requires feedback_loop: true"
            )
        if edge.get("type") == "causes" and "owner" not in edge:
            violations.append(
                f"{errors.INVARIANT_VIOLATION}: {path}.owner is required for a causes edge"
            )
    nodes = {
        node.get("id") for node in graph.get("nodes", []) if isinstance(node, dict)
    }
    for index, edge in enumerate(graph.get("edges", [])):
        for endpoint in ("source", "target"):
            if edge.get(endpoint) not in nodes:
                violations.append(
                    f"{errors.INVARIANT_VIOLATION}: dangling reference, {path_prefix}[{index}].{endpoint} "
                    f"names {edge.get(endpoint)!r}, which is not a node in this graph"
                )
    return violations


def graph_invariants(case: dict, load) -> list[str]:
    graph = load(case["artifact"])
    for key in case.get("at", []):
        graph = graph[key]
    for mutation in case.get("mutate", []):
        container = graph
        for key in mutation["path"][:-1]:
            container = container[key]
        container[mutation["path"][-1]] = mutation["value"]
    violations = schema.validate(
        graph, schema.load_schema("graph.schema.json"), current="graph.schema.json"
    )
    if not violations:
        violations.extend(graph_violations(graph))
    outcome = "invalid" if violations else "valid"
    expect = case["expect"]
    errors_found: list[str] = []
    if outcome != expect["outcome"]:
        errors_found.append(f"graph is {outcome}, case expects {expect['outcome']}: {violations}")
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in violations):
            errors_found.append(f"expected a violation naming {fragment}, got {violations}")
    return errors_found
