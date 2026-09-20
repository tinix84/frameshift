#!/usr/bin/env python3
"""Tests for the application reducer (#225, ADR-0004, ADR-0013).

The harness has a reference reducer and measures implementations against it.
This is the implementation. It must fold the committed reference history to
the reference checkpoint's exact state digest, and it must refuse what the
reference refuses - a log that is not a history, an event the vocabulary does
not know, a revision that does not follow.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.contracts import errors  # noqa: E402
from frameshift.orchestration import replay  # noqa: E402
from frameshift.persistence import canonical  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures"


def reference_events() -> list[dict]:
    text = (FIXTURES / "reference.events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def reference_checkpoint() -> dict:
    return json.loads((FIXTURES / "reference.checkpoint.json").read_text(encoding="utf-8"))


def start_snapshot() -> dict:
    return json.loads((FIXTURES / "replay-start.snapshot.json").read_text(encoding="utf-8"))


class FoldingTheReferenceHistory(unittest.TestCase):
    def test_reaches_the_reference_checkpoints_exact_state_digest(self) -> None:
        state = replay.fold(reference_events())
        self.assertEqual(canonical.digest(state), reference_checkpoint()["state_digest"])

    def test_reaches_the_reference_state_field_by_field(self) -> None:
        """The digest says they agree; this says where, if they ever do not."""
        self.assertEqual(replay.fold(reference_events()), reference_checkpoint()["state"])

    def test_the_fold_ends_at_the_checkpoints_cursor(self) -> None:
        events = reference_events()
        self.assertEqual(len(events), reference_checkpoint()["event_cursor"])

    def test_events_are_not_mutated_by_folding(self) -> None:
        events = reference_events()
        before = json.dumps(events, sort_keys=True)
        replay.fold(events)
        self.assertEqual(json.dumps(events, sort_keys=True), before)


class ResumingFromASnapshot(unittest.TestCase):
    def test_resuming_after_the_cursor_reaches_the_same_state_as_folding_from_the_start(self) -> None:
        snapshot = start_snapshot()
        events = reference_events()
        resumed = replay.resume(snapshot["state"], snapshot["event_cursor"], events[snapshot["event_cursor"] :])
        self.assertEqual(resumed, replay.fold(events))

    def test_a_suffix_whose_first_sequence_does_not_follow_the_cursor_is_refused(self) -> None:
        snapshot = start_snapshot()
        events = reference_events()
        with self.assertRaises(replay.Refused) as raised:
            replay.resume(snapshot["state"], snapshot["event_cursor"], events[snapshot["event_cursor"] + 1 :])
        self.assertEqual(raised.exception.code, errors.INVARIANT_VIOLATION)

    def test_the_snapshot_state_is_not_mutated(self) -> None:
        snapshot = start_snapshot()
        before = copy.deepcopy(snapshot["state"])
        replay.resume(snapshot["state"], snapshot["event_cursor"], reference_events()[snapshot["event_cursor"] :])
        self.assertEqual(snapshot["state"], before)


class RefusingWhatIsNotAHistory(unittest.TestCase):
    def assert_refused(self, events: list[dict], *, naming: str, code: str = errors.INVARIANT_VIOLATION) -> None:
        with self.assertRaises(replay.Refused) as raised:
            replay.fold(events)
        self.assertEqual(raised.exception.code, code)
        self.assertIn(naming, raised.exception.detail)

    def test_a_dropped_event_reaches_a_different_digest_when_sequence_is_not_checked(self) -> None:
        events = [e for e in reference_events() if e["sequence"] != 4]
        state = replay.fold(events, check_sequence=False)
        self.assertNotEqual(canonical.digest(state), reference_checkpoint()["state_digest"])

    def test_a_dropped_event_is_refused_as_a_sequence_gap_by_default(self) -> None:
        events = [e for e in reference_events() if e["sequence"] != 4]
        self.assert_refused(events, naming="sequence")

    def test_a_reordered_log_is_refused_before_folding(self) -> None:
        events = reference_events()
        events[8], events[9] = events[9], events[8]
        self.assert_refused(events, naming="reordered, truncated, or duplicated")

    def test_an_unknown_event_type_is_an_error_not_a_skip(self) -> None:
        events = reference_events()
        events.append(
            {
                "event_id": "evt_000013",
                "payload": {},
                "schema_version": "1.0.0",
                "sequence": 13,
                "session_id": "sess_reference_001",
                "type": "statement.rewritten",
            }
        )
        self.assert_refused(events, naming="statement.rewritten")

    def test_a_revision_with_no_prior_is_refused(self) -> None:
        events = reference_events()
        events[2]["revision"] = 99
        self.assert_refused(events, naming="revision", code=errors.REVISION_CONFLICT)

    def test_a_repeated_revision_is_refused(self) -> None:
        events = reference_events()
        events[3]["revision"] = 1
        self.assert_refused(events, naming="revision", code=errors.REVISION_CONFLICT)

    def test_a_history_must_begin_with_its_own_creation(self) -> None:
        # Renumbered so the sequence is contiguous: what is wrong is the first event, not the numbering.
        events = reference_events()[1:]
        for position, event in enumerate(events, start=1):
            event["sequence"] = position
        self.assert_refused(events, naming="session.created")

    def test_a_second_creation_is_refused(self) -> None:
        events = reference_events()
        again = copy.deepcopy(events[0])
        again["sequence"] = 13
        again["event_id"] = "evt_000013"
        self.assert_refused(events + [again], naming="session.created")

    def test_an_event_for_another_session_is_refused(self) -> None:
        events = reference_events()
        events[5]["session_id"] = "sess_other"
        self.assert_refused(events, naming="session")

    def test_an_event_naming_an_item_the_log_never_created_is_refused(self) -> None:
        events = reference_events()
        events[2]["payload"]["id"] = "stmt_never"
        self.assert_refused(events, naming="stmt_never")

    def test_every_event_type_in_the_reference_history_has_a_reducer(self) -> None:
        for kind in {e["type"] for e in reference_events()}:
            self.assertIn(kind, replay.EVENT_TYPES, kind)


class TheReducerStaysInsideItsBoundary(unittest.TestCase):
    def test_orchestration_replay_imports_no_persistence_and_no_harness(self) -> None:
        source = (ROOT / "frameshift" / "orchestration" / "replay.py").read_text(encoding="utf-8")
        self.assertNotIn("frameshift.persistence", source)
        self.assertNotIn("evals", source)


if __name__ == "__main__":
    unittest.main()
