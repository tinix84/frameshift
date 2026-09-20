"""The ports orchestration owns and persistence implements (ADR-0015).

ADR-0015's table lets `persistence` import `orchestration.ports` and forbids
`orchestration` importing `persistence` at all. So the shape of a store is
declared here, by the coordinator that depends on it, and a store is whatever
satisfies that shape. Nothing in this module knows how anything is stored.

The event log is the first port. ADR-0013 fixes what it must be: append-only,
one event per line, ordered by a monotonic sequence that starts at one and never
skips or repeats. `transitions.committed_events` already relies on the other
half of the contract — a coordinator emits bodies only, and "sequence, event id,
and the session id are the log's to assign, because only the log knows where
the event lands."
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class EventLogRefused(Exception):
    """A log declined to write or to trust what it read.

    Declared with the port so a coordinator can catch it without knowing which
    store raised it. `code` is a published error code; `detail` says why.
    """

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@runtime_checkable
class EventLog(Protocol):
    """A session's history: appended in commits, read back whole."""

    def append(self, session_id: str, bodies: list[dict], *, revision: int) -> list[dict]:
        """Append one commit's event bodies and return the events as written.

        Each body carries `type` and `payload`. The log assigns `sequence`,
        `event_id`, `session_id` and `schema_version`, and places `revision` on
        the event that carries the commit. Every commit declares the revision
        it advances to; the log refuses one that does not follow. Nothing is
        written unless the whole commit is admitted.
        """

    def read(self, session_id: str) -> list[dict]:
        """Every event of the session in sequence order, or nothing if it has no history."""
