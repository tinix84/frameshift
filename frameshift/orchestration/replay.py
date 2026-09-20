"""The application reducer: a session's history folds to its state (#225).

ADR-0004 promises that replaying events reaches the state a snapshot records,
and ADR-0013 makes the promise testable: the log is the history, a snapshot is
a cache of the fold, and where they disagree the log wins. The evaluation
harness carries a reference reducer that states the property. This is the
application's own, written against the same committed history and measured
against the same digest - importing the reference would make the conformance
check measure an implementation against itself.

Two kinds of refusal, kept apart because they mean different things. A
sequence that skips, repeats or runs out of order means the log is not a
history at all, and it is refused before a single event is applied. A revision
that does not follow the last one means a commit claims a prior state that
never existed. Both are refused loudly; neither is ever skipped, because a
reducer that skipped what it did not understand would produce a state that
matched no history.

Orchestration owns this module (ADR-0015) and imports no persistence. Whether a
snapshot's digest is genuine is the checkpoint's business; `resume` takes state
its caller has already verified and says so in its signature.
"""

from __future__ import annotations

import copy

from frameshift.contracts import errors

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION
REVISION_CONFLICT = errors.REVISION_CONFLICT

# Every event type the reducer understands. An event outside this set is an
# error, never a skip - ADR-0013 says the vocabulary grows deliberately, and a
# test holds this set equal to what the committed reference history uses.
EVENT_TYPES = frozenset(
    {
        "session.created",
        "statement.added",
        "statement.classified",
        "statement.status.changed",
        "graph.node.added",
        "graph.edge.added",
        "frame.added",
        "frame.activated",
        "frame.digest.recorded",
        "phase.changed",
        "approval.recorded",
    }
)

EMPTY_GRAPH = {"schema_version": "1.0.0", "nodes": [], "edges": []}


class ReplayRefused(Exception):
    """The reducer will not fold this: it is not a history, or not this one."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def sequence_violations(events: list[dict], cursor: int = 0) -> list[str]:
    """Why these events are not a contiguous history starting after `cursor`."""
    violations: list[str] = []
    for expected, event in enumerate(events, start=cursor + 1):
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence != expected:
            violations.append(
                f"event {expected} carries sequence {sequence!r}, so the history is "
                "reordered, truncated, or duplicated"
            )
    return violations


def fold(events: list[dict], *, check_sequence: bool = True) -> dict:
    """The state a whole history describes, from its first event."""
    return _replay({}, 0, events, check_sequence=check_sequence)


def resume(state: dict, cursor: int, events: list[dict], *, check_sequence: bool = True) -> dict:
    """The state after applying the events past `cursor` to a verified snapshot state.

    The caller has already checked that `state` is what its digest says it is;
    this trusts that and only refuses events that do not continue it.
    """
    if type(cursor) is not int or cursor < 0:
        raise ReplayRefused(INVARIANT_VIOLATION, f"snapshot cursor {cursor!r} is not a position in a history")
    return _replay(copy.deepcopy(state), cursor, events, check_sequence=check_sequence)


def _replay(state: dict, cursor: int, events: list[dict], *, check_sequence: bool) -> dict:
    if check_sequence:
        violations = sequence_violations(events, cursor)
        if violations:
            raise ReplayRefused(INVARIANT_VIOLATION, "; ".join(violations))
    for event in events:
        _admit(state, event)
        _apply(state, event)
    return state


def _admit(state: dict, event: dict) -> None:
    """Refuse an event that cannot belong at this point in this session's history."""
    kind = event.get("type")
    payload = event.get("payload", {})
    if kind not in EVENT_TYPES:
        raise ReplayRefused(INVARIANT_VIOLATION, f"no reducer for event type {kind!r}")
    if not state:
        if kind != "session.created" or event.get("session_id") != payload.get("id"):
            raise ReplayRefused(INVARIANT_VIOLATION, "a history must begin with its own session.created event")
    else:
        if kind == "session.created":
            raise ReplayRefused(INVARIANT_VIOLATION, "a second session.created cannot reset a history")
        if event.get("session_id") != state.get("id"):
            raise ReplayRefused(
                INVARIANT_VIOLATION,
                f"event {event.get('sequence')!r} belongs to session {event.get('session_id')!r}, "
                f"not {state.get('id')!r}",
            )
    if "revision" in event:
        current = state.get("revision", 0)
        expected = current + 1 if state else 0
        if type(event["revision"]) is not int or event["revision"] != expected:
            raise ReplayRefused(
                REVISION_CONFLICT,
                f"event revision {event['revision']!r} does not follow revision {current}",
            )


def _apply(state: dict, event: dict) -> None:
    kind = event["type"]
    payload = event.get("payload", {})
    if kind == "session.created":
        state.update(copy.deepcopy(payload))
        for collection in ("statements", "frames", "options", "criteria", "approvals"):
            state.setdefault(collection, [])
        state.setdefault("graph", copy.deepcopy(EMPTY_GRAPH))
    elif kind == "statement.added":
        state["statements"].append(copy.deepcopy(payload))
    elif kind == "statement.classified":
        statement = _named(state["statements"], payload["id"])
        statement["primary_role"] = payload["primary_role"]
        statement["secondary_roles"] = list(payload["secondary_roles"])
    elif kind == "statement.status.changed":
        _named(state["statements"], payload["id"])["status"] = payload["status"]
    elif kind == "graph.node.added":
        state["graph"]["nodes"].append(copy.deepcopy(payload))
    elif kind == "graph.edge.added":
        state["graph"]["edges"].append(copy.deepcopy(payload))
    elif kind == "frame.added":
        state["frames"].append(copy.deepcopy(payload))
    elif kind == "frame.activated":
        # One fact, one event: the working frame is the one with status
        # `working`, and `active_frame_id` names it rather than being a
        # second thing that could drift from it.
        for frame in state["frames"]:
            if frame.get("status") == "working":
                frame["status"] = "proposed"
        _named(state["frames"], payload["id"])["status"] = "working"
        state["active_frame_id"] = payload["id"]
    elif kind == "frame.digest.recorded":
        _named(state["frames"], payload["id"])["digest"] = payload["digest"]
    elif kind == "phase.changed":
        state["phase"] = payload["phase"]
    elif kind == "approval.recorded":
        state["approvals"].append(copy.deepcopy(payload))
    else:
        # `_admit` already refuses a type outside EVENT_TYPES; this catches a
        # type admitted there but never given a branch here, so it can still
        # never fall through as a skip.
        raise ReplayRefused(INVARIANT_VIOLATION, f"no reducer for event type {kind!r}")
    if "revision" in event:
        state["revision"] = event["revision"]


def _named(items: list[dict], item_id: str) -> dict:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise ReplayRefused(INVARIANT_VIOLATION, f"event names {item_id!r}, which this history never created")
