"""How much of each graph node rests on fact, derived on read (#274, ADR-0031).

A node's ground set is the distinct bases it rests on. The walk starts at the
node and moves backward along live support edges. It continues through
`inferred` nodes and stops at every other node, and each node where it stops
is a base. The grounding profile, the grounding band and solid ground follow
from the ground set and the challenges on the graph.

Everything here is derived from state, as `derived.frame_set` is. No event
records it, the state digest never covers it, and no command or gate reads
it: it orders and highlights only.
"""

from __future__ import annotations

# ADR-0031: each provenance kind maps to one grounding class.
CLASS_OF_KIND = {
    "observed": "fact",
    "sourced": "fact",
    "inferred": "inference",
    "assumed": "opinion",
    "unknown": "gap",
}
# Weakest first: the order that names the weakest base.
CLASS_ORDER = ("gap", "opinion", "inference", "fact")

# A live node or edge; every other status is broken ground.
LIVE_STATUSES = frozenset({"draft", "proposed", "approved"})
UNDECIDED_STATUSES = frozenset({"draft", "proposed"})

# Edges that carry support, by which end rests on the other.
TARGET_RESTS_ON_SOURCE = frozenset({"supports", "causes", "contributes_to"})

CHALLENGE_STATES = ("open", "answered_by_fact", "answered_by_opinion", "conceded")


def derive(state: dict) -> dict:
    """The grounding profile of every node, and solid ground."""
    graph = state.get("graph", {})
    nodes = {item["id"]: item for item in graph.get("nodes", [])}
    support = _support(nodes, graph.get("edges", []))
    challenges = _challenges(graph.get("edges", []))
    profiles = {node_id: _profile(node_id, nodes, support, challenges) for node_id in sorted(nodes)}
    beneath_solid = {
        base
        for node_id, profile in profiles.items()
        if profile["band"] == "solid"
        for _, base in support.get(node_id, [])
        if base != node_id
    }
    solid_ground = [
        node_id for node_id, profile in profiles.items() if profile["band"] == "solid" and node_id not in beneath_solid
    ]
    return {"nodes": profiles, "solid_ground": solid_ground}


def _support(nodes: dict, edges: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """For each node, the live support edges it rests on, as (edge id, base id)."""
    support: dict[str, list[tuple[str, str]]] = {}
    for item in edges:
        if item.get("status") not in LIVE_STATUSES:
            continue
        kind, source, target = item.get("type"), item.get("source"), item.get("target")
        if kind in TARGET_RESTS_ON_SOURCE or (kind == "tests" and nodes.get(source, {}).get("type") == "evidence"):
            resting, base = target, source
        elif kind == "derived_from":
            resting, base = source, target
        else:
            continue
        if resting in nodes and base in nodes:
            support.setdefault(resting, []).append((item["id"], base))
    return support


def _challenges(edges: list[dict]) -> dict[str, dict[str, list[str]]]:
    """The challenges on each node or edge, by state. A live `contradicts` edge is open on its target."""
    found: dict[str, dict[str, list[str]]] = {}
    for item in edges:
        if item.get("type") == "contradicts" and item.get("status") in LIVE_STATUSES:
            found.setdefault(item["target"], {state: [] for state in CHALLENGE_STATES})["open"].append(item["id"])
    return found


def _walk(start: str, nodes: dict, support: dict) -> tuple[list[str], list[str]]:
    """The bases `start` rests on, and every node and edge the walk crossed past it.

    Each node is visited once, so a base reached by two paths counts once and
    a cycle cannot loop. An `inferred` node that no live support edge reaches
    is a base of class inference.
    """
    bases, crossed = [], []
    seen, stack = {start}, [start]
    while stack:
        current = stack.pop()
        item = nodes[current]
        held_up = support.get(current, [])
        if item.get("status") not in LIVE_STATUSES or _kind(item) != "inferred" or not held_up:
            bases.append(current)
            continue
        for edge_id, base in held_up:
            crossed.append(edge_id)
            if base not in seen:
                seen.add(base)
                crossed.append(base)
                stack.append(base)
    return sorted(bases), crossed


def _profile(node_id: str, nodes: dict, support: dict, challenges: dict) -> dict:
    bases, crossed = _walk(node_id, nodes, support)
    by_class = {name: [] for name in reversed(CLASS_ORDER)}
    for base in bases:
        by_class[CLASS_OF_KIND.get(_kind(nodes[base]), "gap")].append(base)
    broken = [base for base in bases if nodes[base].get("status") not in LIVE_STATUSES]
    own = challenges.get(node_id, {state: [] for state in CHALLENGE_STATES})
    upstream = sorted({found for item in crossed for found in challenges.get(item, {}).get("open", [])})
    if broken:
        weakest = broken[0]
    elif bases:
        weakest = min(bases, key=lambda base: (CLASS_ORDER.index(CLASS_OF_KIND.get(_kind(nodes[base]), "gap")), base))
    else:
        weakest = None
    if broken or own["open"] or own["conceded"] or not by_class["fact"]:
        band = "weak"
    elif len(by_class["fact"]) == len(bases) and not upstream:
        band = "solid"
    else:
        band = "mixed"
    return {
        "band": band,
        "bases": by_class,
        "undecided": [base for base in bases if nodes[base].get("status") in UNDECIDED_STATUSES],
        "broken": broken,
        "challenges": {state: list(own[state]) for state in CHALLENGE_STATES},
        "upstream_open": upstream,
        "weakest": weakest,
    }


def _kind(item: dict) -> str | None:
    provenance = item.get("provenance")
    return provenance.get("kind") if isinstance(provenance, dict) else None
