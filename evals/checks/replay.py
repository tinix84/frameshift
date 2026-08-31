"""Replaying events reproduces the snapshot (ADR-0004, ADR-0013).

ADR-0004 persists immutable domain events with periodic state snapshots, and
promises that replaying post-snapshot events reaches the same state the snapshot
records. Nothing measured it, because what a replay fixture looks like depended
on the storage question — settled by ADR-0013 as append-only JSON lines.

The property is worth stating precisely: history and snapshot must not be able
to disagree. A snapshot is a cache of the fold, so if folding the log produces
anything other than the committed state, one of the two is lying and the digest
is the only thing that will say which.

The reducer below is deliberately a separate code path from the state document.
Reproducing the digest means the event handlers and the state shape still agree;
drift in either fails here rather than in production months later.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from . import canonical, errors

ROOT = Path(__file__).resolve().parents[2]
REPLAY_VIOLATION = errors.INVARIANT_VIOLATION


class UnknownEvent(ValueError):
    """The log carries an event type the reducer does not implement."""


def read_log(relative: str) -> list[dict]:
    """An append-only JSON-lines log, one event per line, blank lines ignored."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _find(items: list[dict], item_id: str) -> dict:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise UnknownEvent(f"event names {item_id!r}, which the log never created")


def _apply(state: dict, event: dict) -> dict:
    kind = event["type"]
    payload = event.get("payload", {})

    if kind == "session.created":
        state.update(copy.deepcopy(payload))
        state.setdefault("statements", [])
        state.setdefault("frames", [])
        state.setdefault("options", [])
        state.setdefault("criteria", [])
        state.setdefault("approvals", [])
        state.setdefault("graph", {"schema_version": "1.0.0", "nodes": [], "edges": []})
    elif kind == "statement.added":
        state["statements"].append(copy.deepcopy(payload))
    elif kind == "statement.classified":
        statement = _find(state["statements"], payload["id"])
        statement["primary_role"] = payload["primary_role"]
        statement["secondary_roles"] = list(payload["secondary_roles"])
    elif kind == "statement.status.changed":
        _find(state["statements"], payload["id"])["status"] = payload["status"]
    elif kind == "graph.node.added":
        state["graph"]["nodes"].append(copy.deepcopy(payload))
    elif kind == "graph.edge.added":
        state["graph"]["edges"].append(copy.deepcopy(payload))
    elif kind == "frame.added":
        state["frames"].append(copy.deepcopy(payload))
    elif kind == "frame.activated":
        # A frame becoming the working frame is one fact, so it is one event:
        # `active_frame_id` is which frame has status `working`, never a second
        # thing that can drift out of step with it.
        for frame in state["frames"]:
            if frame["status"] == "working":
                frame["status"] = "proposed"
        _find(state["frames"], payload["id"])["status"] = "working"
        state["active_frame_id"] = payload["id"]
    elif kind == "frame.digest.recorded":
        _find(state["frames"], payload["id"])["digest"] = payload["digest"]
    elif kind == "phase.changed":
        state["phase"] = payload["phase"]
    elif kind == "approval.recorded":
        state["approvals"].append(copy.deepcopy(payload))
    else:
        raise UnknownEvent(f"no reducer for event type {kind!r}")

    if "revision" in event:
        state["revision"] = event["revision"]
    return state


def fold(events: list[dict]) -> dict:
    """Apply every event in order and return the state they describe."""
    state: dict = {}
    for event in events:
        _apply(state, event)
    return state


def sequence_violations(events: list[dict]) -> list[str]:
    """A log is append-only, so sequences start at one and never skip or repeat."""
    violations: list[str] = []
    for index, event in enumerate(events, start=1):
        if event.get("sequence") != index:
            violations.append(
                f"{REPLAY_VIOLATION}: event {index} carries sequence {event.get('sequence')!r}, "
                "so the log is reordered, truncated, or duplicated"
            )
    return violations


def replay_equivalence(case: dict, load) -> list[str]:
    """Fold the log and assert it reaches the state the snapshot records."""
    checkpoint = load(case["artifact"])
    expect = case["expect"]
    errors_found: list[str] = []

    events = read_log(case["log"])
    for mutation in case.get("mutate", []):
        if mutation["kind"] == "drop":
            events = [item for item in events if item["sequence"] != mutation["sequence"]]
        elif mutation["kind"] == "swap":
            first, second = mutation["sequences"]
            index, other = first - 1, second - 1
            events[index], events[other] = events[other], events[index]
        else:
            return [f"unknown mutation kind: {mutation['kind']} (known: drop, swap)"]

    violations = sequence_violations(events) if expect.get("check_sequence", True) else []
    try:
        replayed = fold(events)
    except (UnknownEvent, KeyError) as exc:
        violations.append(f"{REPLAY_VIOLATION}: replay failed: {exc}")
        replayed = None

    if replayed is not None:
        digest = canonical.digest(replayed)
        recorded = checkpoint["state_digest"]
        if digest != recorded:
            violations.append(
                f"{REPLAY_VIOLATION}: replay reached {digest}, the snapshot records {recorded}"
            )
        cursor = checkpoint.get("event_cursor")
        if cursor is not None and cursor != len(events):
            violations.append(
                f"{REPLAY_VIOLATION}: the snapshot's event_cursor is {cursor}, "
                f"the log carries {len(events)} events"
            )

    outcome = "diverged" if violations else "equivalent"
    if outcome != expect["outcome"]:
        errors_found.append(
            f"replay is {outcome}, case expects {expect['outcome']}: {violations or 'no divergence'}"
        )
    for fragment in expect.get("violations_naming", []):
        if not any(fragment in item for item in violations):
            errors_found.append(f"expected a violation naming {fragment}, got {violations}")
    return errors_found
