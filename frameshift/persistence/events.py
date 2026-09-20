"""The append-only JSON-lines event log (#224, ADR-0013, ADR-0015).

One file per session, one event per line, UTF-8, LF-terminated, keys sorted —
the same encoding as the committed reference history, so a diff of two logs is
a diff of events. The store assigns what only it can know: the sequence an
event lands at, its id, its session, and which event of a commit carries the
revision. It refuses, before writing a byte, anything that would make the file
stop being a history: a body that names a sequence other than the next one, a
revision that does not follow the last committed one, a body for another
session, or an empty commit.

This module makes no policy judgement. Whether a transition may happen, whether
an approval binds, whether a proposal is stale — those are orchestration's
(ADR-0015, and the reason #209 exists). What is enforced here is the shape of a
log and nothing else.

Two rules from the reference history, kept rather than invented. Creation
carries its revision on `session.created` itself, so a fresh log begins at
revision zero on its first line; every later commit carries its revision on
its last event. And a revision is optimistic-concurrency state, not phase: it
advances by exactly one per commit, whatever the commit contains.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from frameshift.contracts import errors

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION
REVISION_CONFLICT = errors.REVISION_CONFLICT
SCHEMA_INVALID = errors.SCHEMA_INVALID

SCHEMA_VERSION = "1.0.0"

# `common.schema.json` ids may contain `:`, which is not a legal filename
# character on Windows. A session whose history is a file therefore has the
# narrower shape below; anything else is refused rather than mangled, because
# two ids that mangle to one filename would share a history.
FILENAME_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")

# What the log assigns. A caller-supplied value is dropped, not honoured; the
# one exception is `sequence`, which is checked and then dropped, so a body
# replayed from another runtime can assert where it expects to land.
ASSIGNED = ("event_id", "session_id", "schema_version", "revision")


class Refused(Exception):
    """The log declined to write or to trust what it read."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def encode_line(event: dict) -> str:
    """One event as one line, in the committed fixture's exact encoding."""
    return json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"


class JsonlEventLog:
    """`orchestration.ports.EventLog` over a directory of per-session files."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def path(self, session_id: str) -> Path:
        if not FILENAME_SAFE_ID.match(session_id):
            raise Refused(SCHEMA_INVALID, f"session id {session_id!r} cannot name a history file")
        return self._root / f"{session_id}.events.jsonl"

    def read(self, session_id: str) -> list[dict]:
        path = self.path(session_id)
        if not path.exists():
            return []
        history: list[dict] = []
        raw = path.read_bytes().decode("utf-8")
        for number, line in enumerate(raw.split("\n"), start=1):
            if line == "":
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise Refused(SCHEMA_INVALID, f"line {number} is not one JSON event: {exc.msg}") from None
            if not isinstance(event, dict):
                raise Refused(SCHEMA_INVALID, f"line {number} is not one JSON event")
            history.append(event)
        _refuse_unless_a_history(history, session_id)
        return history

    def append(self, session_id: str, bodies: list[dict], *, revision: int | None = None) -> list[dict]:
        if not bodies:
            raise Refused(INVARIANT_VIOLATION, "a commit must carry at least one event")
        for index, body in enumerate(bodies):
            if not isinstance(body, dict) or not isinstance(body.get("type"), str) or not isinstance(body.get("payload"), dict):
                raise Refused(SCHEMA_INVALID, f"body {index} must carry a string type and an object payload")

        history = self.read(session_id)
        next_sequence = len(history) + 1
        fresh = not history

        last_revision = _last_revision(history)
        if fresh:
            if revision != 0:
                raise Refused(REVISION_CONFLICT, f"a new history begins at revision 0, not {revision!r}")
        elif revision is not None and revision != last_revision + 1:
            raise Refused(
                REVISION_CONFLICT,
                f"commit declares revision {revision} but the history is at {last_revision}",
            )

        # Creation carries its revision on its own event; every later commit
        # carries it on its last event. Both are the reference history's rule.
        carrier = 0 if fresh and bodies[0]["type"] == "session.created" else len(bodies) - 1

        written: list[dict] = []
        for offset, body in enumerate(bodies):
            sequence = next_sequence + offset
            if "sequence" in body and body["sequence"] != sequence:
                raise Refused(
                    INVARIANT_VIOLATION,
                    f"body names sequence {body['sequence']!r} but the next sequence is {sequence}",
                )
            if "session_id" in body and body["session_id"] != session_id:
                raise Refused(INVARIANT_VIOLATION, f"body belongs to session {body['session_id']!r}, not {session_id!r}")
            event = {
                "event_id": f"evt_{sequence:06d}",
                "payload": copy.deepcopy(body["payload"]),
                "schema_version": SCHEMA_VERSION,
                "sequence": sequence,
                "session_id": session_id,
                "type": body["type"],
            }
            if offset == carrier and revision is not None:
                event["revision"] = revision
            written.append(event)

        path = self.path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = "".join(encode_line(event) for event in written).encode("utf-8")
        with path.open("ab") as handle:
            handle.write(encoded)
        return written


def _last_revision(history: list[dict]) -> int:
    """The revision the history is at: the last one any event carried."""
    for event in reversed(history):
        if "revision" in event:
            return event["revision"]
    return 0


def _refuse_unless_a_history(history: list[dict], session_id: str) -> None:
    """ADR-0013: a log that skipped, repeated or reordered is not a log with a gap."""
    for index, event in enumerate(history, start=1):
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence != index:
            raise Refused(
                INVARIANT_VIOLATION,
                f"event {index} carries sequence {sequence!r}, so the history is reordered, truncated, or duplicated",
            )
        if event.get("session_id") != session_id:
            raise Refused(
                INVARIANT_VIOLATION,
                f"event {index} belongs to session {event.get('session_id')!r}, not {session_id!r}",
            )
