#!/usr/bin/env python3
"""Tests that replay equivalence would fail if history and snapshot disagreed.

The fixture proves the committed log folds to the committed snapshot. These
prove the fold is a real reducer rather than a copy of the state document, that
truncation and reordering are caught, and that an unknown event type stops the
replay instead of being skipped.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import canonical, replay  # noqa: E402

LOG = "evals/fixtures/reference.events.jsonl"
REFERENCE = "evals/fixtures/reference.checkpoint.json"


def events() -> list[dict]:
    return replay.read_log(LOG)


class LogShapeTests(unittest.TestCase):
    def test_the_log_is_one_event_per_line_in_sequence(self) -> None:
        log = events()
        self.assertEqual([item["sequence"] for item in log], list(range(1, len(log) + 1)))
        self.assertEqual(replay.sequence_violations(log), [])

    def test_the_log_length_matches_the_snapshots_event_cursor(self) -> None:
        self.assertEqual(len(events()), run.load(REFERENCE)["event_cursor"])

    def test_every_event_names_its_session_and_type(self) -> None:
        session_id = run.load(REFERENCE)["state"]["id"]
        for event in events():
            with self.subTest(sequence=event["sequence"]):
                self.assertEqual(event["session_id"], session_id)
                self.assertTrue(event["type"])
                self.assertTrue(event["event_id"])

    def test_revision_advances_only_on_committed_transitions(self) -> None:
        """Sequence counts events; revision counts commits, and they differ here."""
        log = events()
        revisions = [item["revision"] for item in log if "revision" in item]
        self.assertEqual(revisions, sorted(revisions))
        self.assertLess(len(revisions), len(log))
        self.assertEqual(revisions[-1], run.load(REFERENCE)["state"]["revision"])


class FoldTests(unittest.TestCase):
    def test_the_fold_reproduces_the_recorded_state_digest(self) -> None:
        folded = replay.fold(events())
        self.assertEqual(canonical.digest(folded), run.load(REFERENCE)["state_digest"])

    def test_the_fold_reproduces_the_state_itself_and_not_only_its_digest(self) -> None:
        folded = replay.fold(events())
        state = run.load(REFERENCE)["state"]
        self.assertEqual(canonical.canonicalize(folded), canonical.canonicalize(state))

    def test_dropping_any_single_event_changes_the_result(self) -> None:
        """Every event in the log earns its place."""
        baseline = canonical.digest(replay.fold(events()))
        for dropped in range(1, len(events()) + 1):
            with self.subTest(sequence=dropped):
                remaining = [item for item in events() if item["sequence"] != dropped]
                try:
                    digest = canonical.digest(replay.fold(remaining))
                except (replay.UnknownEvent, KeyError):
                    continue  # the fold could not even complete, which is a stronger failure
                self.assertNotEqual(digest, baseline, f"event {dropped} changed nothing")

    def test_an_unknown_event_type_raises_rather_than_being_skipped(self) -> None:
        log = events()
        log.append(dict(log[-1], sequence=len(log) + 1, type="something.invented"))
        with self.assertRaises(replay.UnknownEvent):
            replay.fold(log)

    def test_an_event_naming_something_never_created_raises(self) -> None:
        log = [item for item in events() if item["type"] != "frame.added"]
        with self.assertRaises(replay.UnknownEvent):
            replay.fold(log)


class SequenceTests(unittest.TestCase):
    def test_a_reordered_log_is_refused(self) -> None:
        log = events()
        log[8], log[9] = log[9], log[8]
        self.assertTrue(replay.sequence_violations(log))

    def test_a_duplicated_event_is_refused(self) -> None:
        log = events()
        log.insert(3, copy.deepcopy(log[3]))
        self.assertTrue(replay.sequence_violations(log))

    def test_a_truncated_log_is_refused_by_the_cursor(self) -> None:
        case = run.load("evals/fixtures/replay-reproduces-the-snapshot.case.json")
        case["mutate"] = [{"kind": "drop", "sequence": 12}]
        case["expect"] = {"outcome": "diverged", "check_sequence": False}
        self.assertEqual(run.evaluate(case), [])


class CaseWiringTests(unittest.TestCase):
    def test_every_declared_case_passes(self) -> None:
        for name in (
            "replay-reproduces-the-snapshot",
            "replay-with-a-dropped-event-diverges",
            "replay-out-of-order-is-refused",
        ):
            with self.subTest(case=name):
                self.assertEqual(run.evaluate(run.load(f"evals/fixtures/{name}.case.json")), [])

    def test_the_equivalence_case_fails_if_the_snapshot_moves(self) -> None:
        case = run.load("evals/fixtures/replay-reproduces-the-snapshot.case.json")

        def load(relative: str) -> object:
            artifact = run.load(relative)
            if relative == case["artifact"]:
                artifact = dict(artifact, state_digest="sha256:" + "0" * 64)
            return artifact

        errors = replay.replay_equivalence(case, load)
        self.assertTrue(any("the snapshot records" in item for item in errors), errors)

    def test_an_unknown_mutation_kind_is_named(self) -> None:
        case = run.load("evals/fixtures/replay-reproduces-the-snapshot.case.json")
        case["mutate"] = [{"kind": "teleport"}]
        errors = run.evaluate(case)
        self.assertTrue(any("unknown mutation kind" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
