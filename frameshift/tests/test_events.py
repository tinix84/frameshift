#!/usr/bin/env python3
"""Tests for the append-only event log (#224, ADR-0013, ADR-0015).

The log is the history. A coordinator hands it event bodies — type and payload —
and the log alone assigns sequence, event id, session id and, on the last event
of a commit, the revision. These tests observe the log only through what it
writes and what it reads back, never through its internals.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.contracts import errors  # noqa: E402
from frameshift.orchestration import ports  # noqa: E402
from frameshift.persistence import events  # noqa: E402

ID_PATTERN = re.compile(
    json.loads((ROOT / "schemas" / "common.schema.json").read_text(encoding="utf-8"))["$defs"]["id"]["pattern"]
)
REFERENCE_LOG = ROOT / "evals" / "fixtures" / "reference.events.jsonl"

SESSION = "sess_test_001"


def created() -> dict:
    return {
        "type": "session.created",
        "payload": {
            "id": SESSION,
            "workspace_id": "ws_test",
            "title": "A request",
            "status": "active",
            "phase": "intake",
            "revision": 0,
            "schema_version": "1.0.0",
            "graph": {"schema_version": "1.0.0", "nodes": [], "edges": []},
        },
    }


def added() -> dict:
    return {
        "type": "statement.added",
        "payload": {
            "id": "stmt_001",
            "text": "Switch the pack to prismatic cells so we hit the cost target.",
            "status": "draft",
            "provenance": {"kind": "observed", "source_ids": ["intake_001"]},
        },
    }


def classified() -> dict:
    return {
        "type": "statement.classified",
        "payload": {"id": "stmt_001", "primary_role": "proposal", "secondary_roles": ["question"]},
    }


class LogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.log = events.JsonlEventLog(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def path(self) -> Path:
        return self.log.path(SESSION)


class AppendAssignsTheLogsOwnFields(LogTestCase):
    def test_a_first_commit_is_numbered_from_one_and_carries_its_revision_last(self) -> None:
        written = self.log.append(SESSION, [created(), added()], revision=0)
        self.assertEqual([e["sequence"] for e in written], [1, 2])
        self.assertEqual([e["session_id"] for e in written], [SESSION, SESSION])
        self.assertEqual([e["type"] for e in written], ["session.created", "statement.added"])
        self.assertIn("revision", written[0])  # creation carries revision zero on its own event
        self.assertEqual(written[0]["revision"], 0)
        self.assertNotIn("revision", written[1])

    def test_a_later_commit_continues_the_sequence_and_puts_the_revision_on_its_last_event(self) -> None:
        self.log.append(SESSION, [created(), added()], revision=0)
        written = self.log.append(SESSION, [classified()], revision=1)
        self.assertEqual(written[0]["sequence"], 3)
        self.assertEqual(written[0]["revision"], 1)

    def test_a_multi_event_commit_carries_the_revision_only_on_the_last_event(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        first, second = self.log.append(SESSION, [added(), classified()], revision=1)
        self.assertNotIn("revision", first)
        self.assertEqual(second["revision"], 1)

    def test_event_ids_are_unique_schema_valid_and_not_the_callers_to_choose(self) -> None:
        body = added()
        body["event_id"] = "evt_i_chose_this"
        written = self.log.append(SESSION, [created(), body], revision=0)
        ids = [e["event_id"] for e in written]
        self.assertEqual(len(set(ids)), 2)
        self.assertNotIn("evt_i_chose_this", ids)
        for event_id in ids:
            self.assertRegex(event_id, ID_PATTERN)

    def test_every_written_event_has_the_reference_shape(self) -> None:
        written = self.log.append(SESSION, [created()], revision=0)
        reference_keys = set(json.loads(REFERENCE_LOG.read_text(encoding="utf-8").splitlines()[0]))
        self.assertEqual(set(written[0]), reference_keys)
        self.assertEqual(written[0]["schema_version"], "1.0.0")

    def test_bodies_are_not_mutated_by_appending(self) -> None:
        body = created()
        before = json.dumps(body, sort_keys=True)
        self.log.append(SESSION, [body], revision=0)
        self.assertEqual(json.dumps(body, sort_keys=True), before)


class AppendRefusesWhatWouldBreakTheHistory(LogTestCase):
    def assert_refused(self, fn, *, code: str = errors.INVARIANT_VIOLATION) -> events.Refused:
        with self.assertRaises(events.Refused) as raised:
            fn()
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_a_body_that_names_a_sequence_which_does_not_follow_is_refused_and_nothing_lands(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        bytes_before = self.path().read_bytes()
        body = added()
        body["sequence"] = 5
        self.assert_refused(lambda: self.log.append(SESSION, [body], revision=1))
        self.assertEqual(self.path().read_bytes(), bytes_before)

    def test_a_body_that_names_the_correct_next_sequence_is_accepted(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        body = added()
        body["sequence"] = 2
        written = self.log.append(SESSION, [body], revision=1)
        self.assertEqual(written[0]["sequence"], 2)

    def test_a_revision_that_does_not_follow_the_last_committed_one_is_refused(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        self.assert_refused(lambda: self.log.append(SESSION, [added()], revision=2), code=errors.REVISION_CONFLICT)
        self.assert_refused(lambda: self.log.append(SESSION, [added()], revision=0), code=errors.REVISION_CONFLICT)

    def test_a_fresh_log_must_begin_at_revision_zero(self) -> None:
        self.assert_refused(lambda: self.log.append(SESSION, [created()], revision=1), code=errors.REVISION_CONFLICT)
        self.assertFalse(self.path().exists())

    def test_a_body_for_another_session_is_refused(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        body = added()
        body["session_id"] = "sess_other"
        self.assert_refused(lambda: self.log.append(SESSION, [body], revision=1))

    def test_an_empty_commit_is_refused(self) -> None:
        self.assert_refused(lambda: self.log.append(SESSION, [], revision=0))

    def test_a_body_without_a_type_or_payload_is_refused(self) -> None:
        self.assert_refused(lambda: self.log.append(SESSION, [{"payload": {}}], revision=0), code=errors.SCHEMA_INVALID)
        self.assert_refused(lambda: self.log.append(SESSION, [{"type": "x"}], revision=0), code=errors.SCHEMA_INVALID)


class ReadReturnsTheHistoryOrRefusesIt(LogTestCase):
    def test_read_returns_exactly_what_was_written_in_order(self) -> None:
        first = self.log.append(SESSION, [created(), added()], revision=0)
        second = self.log.append(SESSION, [classified()], revision=1)
        self.assertEqual(self.log.read(SESSION), first + second)

    def test_reading_a_session_with_no_history_returns_nothing(self) -> None:
        self.assertEqual(self.log.read("sess_never_opened"), [])

    def test_a_skipped_sequence_on_disk_is_refused_on_read(self) -> None:
        self.log.append(SESSION, [created(), added(), classified()], revision=0)
        lines = self.path().read_text(encoding="utf-8").splitlines()
        self.path().write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        with self.assertRaises(events.Refused) as raised:
            self.log.read(SESSION)
        self.assertEqual(raised.exception.code, errors.INVARIANT_VIOLATION)

    def test_a_repeated_sequence_on_disk_is_refused_on_read(self) -> None:
        self.log.append(SESSION, [created(), added()], revision=0)
        lines = self.path().read_text(encoding="utf-8").splitlines()
        self.path().write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8")
        with self.assertRaises(events.Refused):
            self.log.read(SESSION)

    def test_a_reordered_log_on_disk_is_refused_on_read(self) -> None:
        self.log.append(SESSION, [created(), added()], revision=0)
        lines = self.path().read_text(encoding="utf-8").splitlines()
        self.path().write_text("\n".join([lines[1], lines[0]]) + "\n", encoding="utf-8")
        with self.assertRaises(events.Refused):
            self.log.read(SESSION)

    def test_a_line_that_is_not_json_is_refused_by_line(self) -> None:
        self.log.append(SESSION, [created()], revision=0)
        with self.path().open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        with self.assertRaises(events.Refused) as raised:
            self.log.read(SESSION)
        self.assertEqual(raised.exception.code, errors.SCHEMA_INVALID)
        self.assertIn("line 2", raised.exception.detail)

    def test_the_committed_reference_history_reads_cleanly(self) -> None:
        """The reference log is a valid log by this store's rules, not only the harness's."""
        target = self.log.path("sess_reference_001")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(REFERENCE_LOG.read_bytes())
        history = self.log.read("sess_reference_001")
        self.assertEqual(len(history), 12)
        self.assertEqual([e["sequence"] for e in history], list(range(1, 13)))

    def test_appending_after_the_reference_history_continues_it(self) -> None:
        target = self.log.path("sess_reference_001")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(REFERENCE_LOG.read_bytes())
        written = self.log.append("sess_reference_001", [classified()], revision=5)
        self.assertEqual(written[0]["sequence"], 13)
        self.assertEqual(written[0]["revision"], 5)


class TheFileIsOneEventPerLine(LogTestCase):
    def test_utf8_one_json_object_per_line_lf_terminated_sorted_keys(self) -> None:
        body = added()
        body["payload"]["text"] = "Zellen — für die Kostenvorgabe ✓"
        self.log.append(SESSION, [created(), body], revision=0)
        raw = self.path().read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))
        lines = raw.decode("utf-8").split("\n")
        self.assertEqual(lines[-1], "")
        self.assertEqual(len(lines) - 1, 2)
        for line in lines[:-1]:
            parsed = json.loads(line)
            self.assertEqual(list(parsed), sorted(parsed))
        self.assertIn("Zellen — für die Kostenvorgabe ✓", lines[1])

    def test_a_written_line_is_byte_identical_to_the_reference_encoding(self) -> None:
        """Same encoding as the committed fixture, so a diff of two logs is a diff of events."""
        reference_first = REFERENCE_LOG.read_text(encoding="utf-8").splitlines()[0]
        reference = json.loads(reference_first)
        # Re-encode the reference event with this store's encoder and compare bytes.
        self.assertEqual(events.encode_line(reference), reference_first + "\n")


class TheStoreStaysBelowOrchestration(unittest.TestCase):
    """ADR-0015: persistence may import orchestration.ports and nothing else of orchestration."""

    def test_persistence_events_imports_only_the_port_from_orchestration(self) -> None:
        source = (ROOT / "frameshift" / "persistence" / "events.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("frameshift.orchestration"):
                if node.module != "frameshift.orchestration.ports":
                    offenders.append(node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("frameshift.orchestration"):
                        offenders.append(alias.name)
        self.assertEqual(offenders, [])

    def test_the_port_module_imports_no_persistence(self) -> None:
        source = (ROOT / "frameshift" / "orchestration" / "ports.py").read_text(encoding="utf-8")
        self.assertNotIn("frameshift.persistence", source)

    def test_the_store_satisfies_the_port(self) -> None:
        self.assertTrue(isinstance(events.JsonlEventLog(Path(tempfile.gettempdir())), ports.EventLog))


if __name__ == "__main__":
    unittest.main()
