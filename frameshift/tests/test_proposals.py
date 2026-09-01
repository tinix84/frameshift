#!/usr/bin/env python3
"""Tests for proposal staleness (#24).

The rule is one line of #24 — long executions pin an input revision, and their
results become stale proposals if the session advances. These hold the three
states apart, and hold the line that stale is not the same as discarded.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration import proposals, transitions  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures"


def result() -> dict:
    return json.loads((FIXTURES / "framing-solution-disguised.result.json").read_text(encoding="utf-8"))


def session(revision: int) -> dict:
    state = json.loads((FIXTURES / "reference.checkpoint.json").read_text(encoding="utf-8"))["state"]
    state["revision"] = revision
    return state


class StalenessTests(unittest.TestCase):
    def test_a_result_at_the_session_revision_is_current(self) -> None:
        self.assertEqual(proposals.staleness(result(), session(1)), "current")

    def test_a_result_behind_the_session_is_stale(self) -> None:
        self.assertEqual(proposals.staleness(result(), session(4)), "stale")

    def test_a_result_ahead_of_the_session_is_impossible(self) -> None:
        """It claims to have seen state that does not exist."""
        self.assertEqual(proposals.staleness(result(), session(0)), "impossible")

    def test_a_missing_revision_is_impossible_not_current(self) -> None:
        stripped = {key: value for key, value in result().items() if key != "input_revision"}
        self.assertEqual(proposals.staleness(stripped, session(1)), "impossible")


class AdmissionTests(unittest.TestCase):
    def test_a_current_result_is_admitted(self) -> None:
        outcome = proposals.admit(result(), session(1))
        self.assertEqual(outcome["outcome"], "admitted")
        self.assertEqual(outcome["refusals"], [])

    def test_a_stale_result_is_held_with_a_revision_conflict(self) -> None:
        outcome = proposals.admit(result(), session(4))
        self.assertEqual(outcome["outcome"], "held")
        self.assertTrue(
            any(item.startswith(transitions.REVISION_CONFLICT) for item in outcome["refusals"]),
            outcome["refusals"],
        )

    def test_the_refusal_names_both_revisions_and_the_gap(self) -> None:
        message = proposals.admit(result(), session(4))["refusals"][0]
        for fragment in ("revision 1", "is at 4", "3 revisions later"):
            self.assertIn(fragment, message)

    def test_one_revision_behind_reads_in_the_singular(self) -> None:
        self.assertIn("1 revision later", proposals.admit(result(), session(2))["refusals"][0])

    def test_a_result_ahead_of_the_session_is_an_invariant_violation(self) -> None:
        outcome = proposals.admit(result(), session(0))
        self.assertTrue(
            any(item.startswith(transitions.INVARIANT_VIOLATION) for item in outcome["refusals"]),
            outcome["refusals"],
        )

    def test_a_held_result_keeps_its_proposals(self) -> None:
        """Stale is not discarded — a human may still want to read them."""
        held = proposals.admit(result(), session(4))
        admitted = proposals.admit(result(), session(1))
        self.assertEqual(held["proposal_ids"], admitted["proposal_ids"])
        self.assertEqual(len(held["proposal_ids"]), 3)

    def test_every_refusal_code_is_published_in_the_vocabulary(self) -> None:
        sys.path.insert(0, str(ROOT))
        from evals.checks import errors

        for revision in (0, 4):
            with self.subTest(revision=revision):
                for refusal in proposals.admit(result(), session(revision))["refusals"]:
                    self.assertIn(refusal.split(":", 1)[0], errors.PUBLISHED)


class BoundaryTests(unittest.TestCase):
    def test_this_is_a_different_guard_from_approval_staleness(self) -> None:
        """ADR-0002 stops a human approving A while B commits; this is the reverse."""
        self.assertNotEqual(transitions.REVISION_CONFLICT, transitions.APPROVAL_STALE)

    def test_the_adapter_port_checks_the_request_and_this_checks_the_session(self) -> None:
        """The two revision checks answer different questions and both are needed."""
        from frameshift.adapters import EchoAdapter, run

        request = json.loads((FIXTURES / "reference.execution-request.json").read_text(encoding="utf-8"))
        outcome = run(EchoAdapter(result()), request)
        self.assertTrue(outcome.accepted, outcome.violations)
        # The adapter normalized the result onto the request's revision, and the
        # session has since moved on — so the port is satisfied and this is not.
        self.assertEqual(
            proposals.staleness(outcome.result, session(request["session_revision"] + 1)), "stale"
        )


if __name__ == "__main__":
    unittest.main()
