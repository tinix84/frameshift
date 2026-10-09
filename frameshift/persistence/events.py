"""The append-only JSON-lines event log (#224, ADR-0013, ADR-0015).

One file per session, one event per line, UTF-8, LF-terminated, keys sorted —
the same encoding as the committed reference history, so a diff of two logs is
a diff of events. The store assigns what only it can know: the sequence an
event lands at, its id, its session, and which event of a commit carries the
revision. It refuses, before writing a byte, anything that would make the file
stop being a history: a body that names a sequence other than the next one, a
revision that does not follow the last committed one, a body for another
session, or an empty commit.

ADR-0015 asks for more than a check: two commits based on one revision must
not both land, and a commit is visible whole or not at all. Both are earned
here rather than assumed of a file append (#172):

- A commit holds an exclusive operating-system lock on the session's sidecar
  `.lock` file while it reads the history, checks the revision and writes. A
  second writer at the same revision waits, then reads the advanced history
  and is refused with `revision_conflict`. The lock dies with its process, so
  a crash cannot leave a stale one.
- The new history (the old bytes, unchanged, then the commit) is written to a
  `.pending` file, flushed to disk, and moved over the history with
  `os.replace`, which is atomic on one volume. An interruption before the move
  leaves the previous history intact and the next commit overwrites the
  orphan; nothing ever reads half a commit. Line-level detection could not do
  this: the creation commit carries its revision on its first event, so a
  torn creation commit would read back as a whole one.

A file torn by an older writer is still refused on read: a truncated last line
is not JSON and a missing one breaks the sequence.

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

import contextlib
import copy
import json
import os
import re
from pathlib import Path

from frameshift.contracts import errors
from frameshift.orchestration.ports import EventLogRefused

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION
REVISION_CONFLICT = errors.REVISION_CONFLICT
SCHEMA_INVALID = errors.SCHEMA_INVALID

SCHEMA_VERSION = "1.0.0"

# `common.schema.json` ids may contain `:`, which is not a legal filename
# character on Windows. A session whose history is a file therefore has the
# narrower shape below; anything else is refused rather than mangled, because
# two ids that mangle to one filename would share a history.
FILENAME_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")

def encode_line(event: dict) -> str:
    """One event as one line, in the committed fixture's exact encoding."""
    return json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"


class JsonlEventLog:
    """`orchestration.ports.EventLog` over a directory of per-session files."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def path(self, session_id: str) -> Path:
        if not FILENAME_SAFE_ID.match(session_id):
            raise EventLogRefused(SCHEMA_INVALID, f"session id {session_id!r} cannot name a history file")
        return self._root / f"{session_id}.events.jsonl"

    def session_ids(self) -> list[str]:
        """Every session with a history file here, sorted (`orchestration.ports.SessionIndex`)."""
        if not self._root.is_dir():
            return []
        suffix = ".events.jsonl"
        found = []
        for path in sorted(self._root.glob(f"*{suffix}")):
            session_id = path.name[: -len(suffix)]
            if FILENAME_SAFE_ID.match(session_id):
                found.append(session_id)
        return found

    def read(self, session_id: str) -> list[dict]:
        return self._load(session_id)[1]

    def _load(self, session_id: str) -> tuple[bytes, list[dict]]:
        """The history's bytes as stored, and the events they hold."""
        path = self.path(session_id)
        if not path.exists():
            return b"", []
        stored = path.read_bytes()
        history: list[dict] = []
        raw = stored.decode("utf-8")
        for number, line in enumerate(raw.split("\n"), start=1):
            if line == "":
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EventLogRefused(SCHEMA_INVALID, f"line {number} is not one JSON event: {exc.msg}") from None
            if not isinstance(event, dict):
                raise EventLogRefused(SCHEMA_INVALID, f"line {number} is not one JSON event")
            history.append(event)
        _refuse_unless_a_history(history, session_id)
        return stored, history

    def append(self, session_id: str, bodies: list[dict], *, revision: int) -> list[dict]:
        if not bodies:
            raise EventLogRefused(INVARIANT_VIOLATION, "a commit must carry at least one event")
        if type(revision) is not int:
            raise EventLogRefused(SCHEMA_INVALID, f"a commit must declare an integer revision, not {revision!r}")
        for index, body in enumerate(bodies):
            if not isinstance(body, dict) or not isinstance(body.get("type"), str) or not isinstance(body.get("payload"), dict):
                raise EventLogRefused(SCHEMA_INVALID, f"body {index} must carry a string type and an object payload")

        path = self.path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive(path.with_name(path.name + ".lock")):
            stored, history = self._load(session_id)
            written = self._admit(session_id, history, bodies, revision)
            encoded = "".join(encode_line(event) for event in written).encode("utf-8")
            _replace_atomically(path, stored + encoded)
        return written

    def _admit(self, session_id: str, history: list[dict], bodies: list[dict], revision: int) -> list[dict]:
        """The events this commit would write, or a refusal; nothing is written here."""
        next_sequence = len(history) + 1
        fresh = not history

        last_revision = _last_revision(history)
        if fresh:
            if revision != 0:
                raise EventLogRefused(REVISION_CONFLICT, f"a new history begins at revision 0, not {revision!r}")
        elif revision != last_revision + 1:
            raise EventLogRefused(
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
                raise EventLogRefused(
                    INVARIANT_VIOLATION,
                    f"body names sequence {body['sequence']!r} but the next sequence is {sequence}",
                )
            if "session_id" in body and body["session_id"] != session_id:
                raise EventLogRefused(INVARIANT_VIOLATION, f"body belongs to session {body['session_id']!r}, not {session_id!r}")
            event = {
                # Qualified by session, so ids are unique across a store and
                # not only within one file.
                "event_id": f"evt_{session_id}_{sequence:06d}",
                "payload": copy.deepcopy(body["payload"]),
                "schema_version": SCHEMA_VERSION,
                "sequence": sequence,
                "session_id": session_id,
                "type": body["type"],
            }
            if offset == carrier:
                event["revision"] = revision
            written.append(event)
        return written


@contextlib.contextmanager
def _exclusive(lock_path: Path):
    """Hold an exclusive lock on `lock_path` for one commit; released if the process dies."""
    handle = open(lock_path, "a+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt

                # Locks from the current position; retries for about ten seconds, then raises.
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            raise EventLogRefused(REVISION_CONFLICT, f"another commit holds the history: {exc}") from None
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _replace_atomically(path: Path, content: bytes) -> None:
    """Make `content` the history in one step: whole, or not at all."""
    pending = path.with_name(path.name + ".pending")
    with pending.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(pending, path)
    except OSError as exc:
        raise EventLogRefused(INVARIANT_VIOLATION, f"the commit could not replace the history: {exc}") from None


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
            raise EventLogRefused(
                INVARIANT_VIOLATION,
                f"event {index} carries sequence {sequence!r}, so the history is reordered, truncated, or duplicated",
            )
        if event.get("session_id") != session_id:
            raise EventLogRefused(
                INVARIANT_VIOLATION,
                f"event {index} belongs to session {event.get('session_id')!r}, not {session_id!r}",
            )
