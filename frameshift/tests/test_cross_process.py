#!/usr/bin/env python3
"""Two processes, one session log: at most one commit per revision (#286).

The manual GUI and the reasoner's MCP server are separate processes that
write the same event log. ADR-0015 asks that two commits formed against one
revision never both land, and ADR-0013 that the log stays a history. These
tests hold both across operating-system processes, not threads.

Each writer is held at a barrier after its coordinator has read and checked
the revision, just before it appends. Both therefore pass the coordinator's
own check, and only the log's lock and revision check stand between them.
"""

from __future__ import annotations

import itertools
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import reasoner_coordinator  # noqa: E402
from frameshift.orchestration.api import CommandRefused  # noqa: E402
from frameshift.tests.test_sessions import OWNER, REQUEST, coordinator  # noqa: E402
from frameshift.validation import session_violations  # noqa: E402

RUNTIME = {"id": "reasoner_local", "kind": "runtime"}
ROUNDS = 4


class _HeldAtTheBarrier:
    """The real log, with every append held until the other writer arrives."""

    def __init__(self, log, barrier) -> None:
        self._log = log
        self._barrier = barrier

    def append(self, *args, **kwargs):
        self._barrier.wait(timeout=60)
        return self._log.append(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._log, name)


def _writer(role: str, store: str, session_id: str, barrier, results, rounds: int) -> None:
    """One process: the person through the GUI's coordinator, or the reasoner through its own."""
    sys.path.insert(0, str(ROOT))
    if role == "person":
        co = coordinator(Path(store))
    else:
        counter = itertools.count(1)
        co = reasoner_coordinator(Path(store), RUNTIME, new_suffix=lambda: f"r{next(counter):04d}")
    co._log = _HeldAtTheBarrier(co._log, barrier)
    for number in range(rounds):
        # Both writers read the revision only after the previous round settled.
        barrier.wait(timeout=60)
        revision = co.state(session_id)["revision"]
        try:
            if role == "person":
                co.add_operator_statement(
                    session_id, text=f"The person's fact {number}.", primary_role="observation", expected_revision=revision
                )
            else:
                co.add_statement(
                    session_id, text=f"The reasoner's fact {number}.", primary_role="observation", expected_revision=revision
                )
            results.put((role, number, revision, "committed"))
        except CommandRefused as refused:
            results.put((role, number, revision, refused.code))
        barrier.wait(timeout=60)


class TwoProcessesOneLog(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = Path(self._dir.name)
        self.person = coordinator(self.store)
        self.sid = self.person.open_session(title="", request=REQUEST)["state"]["id"]

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_two_writers_at_one_revision_commit_at_most_once(self) -> None:
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        writers = [
            context.Process(target=_writer, args=(role, str(self.store), self.sid, barrier, results, ROUNDS))
            for role in ("person", "reasoner")
        ]
        for writer in writers:
            writer.start()
        outcomes = [results.get(timeout=120) for _ in range(2 * ROUNDS)]
        for writer in writers:
            writer.join(timeout=60)
            self.assertEqual(writer.exitcode, 0)

        for number in range(ROUNDS):
            with self.subTest(round=number):
                seen = sorted(outcome for role, n, revision, outcome in outcomes if n == number)
                formed = {revision for role, n, revision, outcome in outcomes if n == number}
                self.assertEqual(len(formed), 1, "both writers formed their command against one revision")
                self.assertEqual(seen, ["committed", "revision_conflict"])

        history = self.person.history(self.sid)
        state = self.person.state(self.sid)
        self.assertEqual(state["revision"], ROUNDS, "exactly one commit landed per round")
        self.assertEqual([event["sequence"] for event in history], list(range(1, len(history) + 1)))
        self.assertEqual(len(state["statements"]), 1 + ROUNDS)
        self.assertEqual(session_violations(state), [])
        # Each landed statement keeps its writer's provenance: the person's
        # are observed, the reasoner's assumed. Neither borrows the other's.
        landed = [(s["text"].split("'")[0], s["provenance"]["kind"]) for s in state["statements"][1:]]
        self.assertTrue(all(kind == {"The person": "observed", "The reasoner": "assumed"}[who] for who, kind in landed), landed)


class TheServerProcessRefusesAStaleWrite(unittest.TestCase):
    """The real `reasoner` subcommand, a separate process, after the person moved on."""

    def test_a_write_formed_before_the_persons_commit_is_refused_and_never_looks_like_one(self) -> None:
        with tempfile.TemporaryDirectory() as store:
            person = coordinator(Path(store))
            sid = person.open_session(title="", request=REQUEST)["state"]["id"]
            seen = person.state(sid)["revision"]
            person.add_operator_statement(sid, text="The pack misses the target.", primary_role="observation", expected_revision=seen)
            call = {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "frameshift_add_statement", "arguments": {
                    "session_id": sid, "expected_revision": seen, "text": "Cells dominate cost.", "primary_role": "observation"}},
            }
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            done = subprocess.run(
                [sys.executable, "-m", "frameshift.bootstrap", "reasoner", "--store", store],
                input=json.dumps(call) + "\n", capture_output=True, encoding="utf-8", cwd=ROOT, env=env, timeout=60,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            (reply,) = [json.loads(line) for line in done.stdout.splitlines()]
            result = reply["result"]
            self.assertTrue(result["isError"])
            self.assertEqual(result["structuredContent"]["outcome"], "refused")
            self.assertEqual(result["structuredContent"]["code"], "revision_conflict")
            self.assertNotIn("events", result["structuredContent"])
            self.assertEqual(person.state(sid)["revision"], seen + 1, "only the person's commit landed")


if __name__ == "__main__":
    unittest.main()
