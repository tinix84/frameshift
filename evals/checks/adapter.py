"""Provider neutrality is a test result, not a promise (ADR-0001).

One reference checkpoint, two adapters, one digest. Each adapter here is a stub
that round-trips canonical state through a provider-shaped form and back; the
assertion is about the comparison, not about model output, so no provider is
contacted and none is needed.

What the comparison tolerates is the whole content of ADR-0001. Adapters may
order keys differently and may annotate their own namespaced `extensions`,
because neither can alter canonical safety semantics. Anything else an adapter
carries back into state — a provider request ID above all — is a divergence,
and the failure names the JSON path where the two disagree.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from . import canonical

DIVERGENCE = "adapter_state_diverged"

# Where the schemas declare a namespaced `extensions` object. Extensions are
# stripped at these locations and nowhere else before comparing, so an adapter
# annotating its own namespace agrees with one that does not, while an adapter
# inventing an `extensions` key somewhere the schemas do not allow it diverges.
# `evals/test_adapter.py` asserts this list still matches `schemas/`.
EXTENSION_POINTS = (
    ("extensions",),
    ("graph", "nodes", "*", "extensions"),
    ("graph", "edges", "*", "extensions"),
)


def _strip(node: object, path: tuple[str, ...]) -> None:
    """Remove the key `path` names, following `*` through a list."""
    if not path:
        return
    head, rest = path[0], path[1:]
    if head == "*":
        if isinstance(node, list):
            for item in node:
                _strip(item, rest)
        return
    if not isinstance(node, dict):
        return
    if rest:
        _strip(node.get(head), rest)
    else:
        node.pop(head, None)


def neutral(state: dict) -> dict:
    """Canonical state with every provider's namespaced extensions removed."""
    stripped = copy.deepcopy(state)
    for path in EXTENSION_POINTS:
        _strip(stripped, path)
    return stripped


def first_divergence(left: object, right: object, path: str = "$.state") -> str | None:
    """The JSON path where two states first disagree, or None if they agree."""
    if type(left) is not type(right):
        return path
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}"
            found = first_divergence(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return path
        for index, (one, other) in enumerate(zip(left, right)):
            found = first_divergence(one, other, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if left == right else path


# The adapter manifest. Each entry round-trips canonical state through a
# provider-shaped form and back. Adding an adapter means adding an entry here
# and naming it in a case; the runner and the check stay as they are.
def _echo(state: dict) -> dict:
    """The neutral baseline: canonical state in, canonical state out."""
    return state


def _reordering(state: dict) -> dict:
    """A provider whose serializer emits keys in its own order."""
    if isinstance(state, dict):
        return {key: _reordering(state[key]) for key in reversed(list(state))}
    if isinstance(state, list):
        return [_reordering(item) for item in state]
    return state


def _extension_annotating(state: dict) -> dict:
    """A provider that records native detail in its own namespace, as ADR-0001 allows."""
    state["extensions"] = {"x-example-provider": {"native_session": "sess_native_42"}}
    for node in state.get("graph", {}).get("nodes", []):
        node["extensions"] = {"x-example-provider": {"native_node": node["id"]}}
    return state


def _crlf_text(state: dict) -> dict:
    """A provider that serializes text with CRLF line endings."""
    if isinstance(state, dict):
        return {key: _crlf_text(item) for key, item in state.items()}
    if isinstance(state, list):
        return [_crlf_text(item) for item in state]
    if isinstance(state, str):
        return state.replace("\n", "\r\n")
    return state


def _request_id_promoting(state: dict) -> dict:
    """A provider that promotes its request ID into canonical state. This is the bug."""
    state["provider_request_id"] = "req_9f2c"
    return state


ADAPTERS = {
    "crlf_text": _crlf_text,
    "echo": _echo,
    "extension_annotating": _extension_annotating,
    "reordering": _reordering,
    "request_id_promoting": _request_id_promoting,
}


def adapter_round_trip(case: dict, load) -> list[str]:
    """Carry one checkpoint through the named adapters and compare on state_digest."""
    checkpoint = load(case["artifact"])
    names = case.get("adapters", [])
    expect = case["expect"]
    errors: list[str] = []

    if len(names) < 2:
        return ["a round trip needs at least two adapters"]

    states: dict[str, dict] = {}
    for name in names:
        adapter = ADAPTERS.get(name)
        if adapter is None:
            errors.append(f"unknown adapter: {name} (known: {sorted(ADAPTERS)})")
            continue
        states[name] = neutral(adapter(copy.deepcopy(checkpoint["state"])))
    if errors:
        return errors

    baseline_name = names[0]
    baseline = states[baseline_name]
    baseline_digest = canonical.digest(baseline)
    violations: list[str] = []
    for name in names[1:]:
        if canonical.digest(states[name]) == baseline_digest:
            continue
        path = first_divergence(baseline, states[name]) or "$.state"
        violations.append(f"{DIVERGENCE}: {baseline_name} and {name} disagree at {path}")

    outcome = "diverged" if violations else "agreed"
    if outcome != expect["outcome"]:
        # An unexpected divergence carries its paths, so a failing adapter is
        # named by the field it disagreed on rather than by the case's verdict.
        detail = "; ".join(violations) if violations else "no divergence"
        errors.append(f"round trip {outcome}, case expects {expect['outcome']}: {detail}")
    path = expect.get("path")
    if path and not any(item.endswith(path) for item in violations):
        errors.append(f"expected a divergence at {path}, got {violations or 'no divergence'}")

    # The agreed digest is the checkpoint's own recorded `state_digest`, not a
    # second copy of it: provider neutrality means the adapters agree on *the*
    # canonical digest, and one recorded value is one place to re-anchor.
    if outcome == "agreed" and expect.get("is_the_recorded_state_digest"):
        recorded = checkpoint.get("state_digest")
        if baseline_digest != recorded:
            errors.append(
                f"adapters agree on {baseline_digest}, the checkpoint records {recorded}"
            )

    return errors


def corpus_across_adapters(case: dict, load) -> list[str]:
    """Every corpus case, re-run with its artifacts carried through each adapter.

    ADR-0001's promise is not only that two adapters agree on a digest. It is
    that every property the corpus asserts survives the trip: a refusal is still
    a refusal, a repair still refuses to add facts, a gate still cannot be
    crossed. Rather than duplicate a fixture per adapter, the case is re-run
    with a loader that transports whatever it loads, so an adapter is held to
    the corpus that already exists.
    """
    from . import REGISTRY

    transports = case.get("transports", [])
    wanted = set(case.get("corpus", []))
    errors: list[str] = []

    if not transports or not wanted:
        return ['case must name "transports" and "corpus" check names']

    root = Path(__file__).resolve().parents[2]
    corpus = []
    for path in sorted((root / "evals" / "fixtures").glob("*.case.json")):
        with path.open("r", encoding="utf-8") as handle:
            other = json.load(handle)
        if other.get("check") in wanted:
            corpus.append(other)
    if not corpus:
        return [f"no corpus cases declare any of {sorted(wanted)}"]

    for name in transports:
        transport = ADAPTERS.get(name)
        if transport is None:
            errors.append(f"unknown adapter: {name} (known: {sorted(ADAPTERS)})")
            continue
        # The loader is the seam: every artifact a case reads arrives having
        # been through the adapter, and nothing about the case itself changes.
        def transported(relative: str, _transport=transport) -> object:
            return _transport(copy.deepcopy(load(relative)))

        for other in corpus:
            found = REGISTRY[other["check"]](other, transported)
            if found:
                errors.append(f"{name} changed {other['id']}: {found}")

    expect = case.get("expect", {}).get("outcome", "unchanged")
    if expect == "unchanged":
        return errors
    if expect == "changed" and not errors:
        return ["every case survived, the corpus expects at least one to change"]
    return []
