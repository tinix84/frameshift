#!/usr/bin/env python3
"""Tests for the session coordinator (#226, #227, #228, #229).

Each class names the issue whose acceptance criteria it checks. They run the
coordinator against the real JSON-lines store in a temporary directory, because
#229's point is that the fold of what was appended is the session - an
in-memory fake would test a different promise.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import manual_coordinator  # noqa: E402
from frameshift.orchestration.api import CommandRefused  # noqa: E402
from frameshift.orchestration.transitions import content_digest  # noqa: E402
from frameshift.validation import session_violations  # noqa: E402

OWNER = {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"}
REQUEST = "  Switch the pack to prismatic cells\tso we hit the cost target.\n"


def coordinator(store: Path, operator: dict = OWNER):
    counter = itertools.count(1)
    return manual_coordinator(
        store,
        operator,
        clock=lambda: "2026-10-06T09:00:00Z",
        new_suffix=lambda: f"t{next(counter):04d}",
    )


def approve(co, request: dict, disposition: str = "approved") -> dict:
    return co.confirm(
        request["id"],
        {
            "request_id": request["id"],
            "request_digest": request["request_digest"],
            "status": "submitted",
            "disposition": disposition,
            "edited_proposal": None,
        },
    )


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = Path(self._dir.name)
        self.co = coordinator(self.store)
        self.sid = self.co.open_session(title="", request=REQUEST)["state"]["id"]

    def tearDown(self) -> None:
        self._dir.cleanup()

    def classify(self, role: str = "proposal", secondary=("need",)) -> dict:
        result = self.co.manual_framing_result(
            self.sid, [{"statement_id": "stmt_001", "primary_role": role, "secondary_roles": list(secondary)}]
        )
        return self.co.admit_result(self.sid, result)

    def revision(self) -> int:
        return self.co.state(self.sid)["revision"]

    def seal_intake(self) -> None:
        self.classify()
        self.co.add_statement(self.sid, text="Pack cost per usable kWh meets the target.", primary_role="outcome", expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001"))


class OpenASessionFromOneVerbatimRequest(Fixture):
    """#226."""

    def test_opening_emits_exactly_created_then_added(self) -> None:
        self.assertEqual([e["type"] for e in self.co.history(self.sid)], ["session.created", "statement.added"])

    def test_the_request_survives_byte_for_byte(self) -> None:
        self.assertEqual(self.co.state(self.sid)["statements"][0]["text"], REQUEST)

    def test_the_statement_is_draft_and_observed_from_one_intake_source(self) -> None:
        statement = self.co.state(self.sid)["statements"][0]
        self.assertEqual(statement["status"], "draft")
        self.assertEqual(statement["provenance"]["kind"], "observed")
        self.assertEqual(len(statement["provenance"]["source_ids"]), 1)
        self.assertTrue(statement["provenance"]["source_ids"][0].startswith("intake_"))

    def test_the_session_starts_empty_at_revision_zero_in_intake(self) -> None:
        state = self.co.state(self.sid)
        self.assertEqual((state["revision"], state["phase"], state["status"]), (0, "intake", "active"))
        for collection in ("frames", "options", "criteria", "approvals"):
            self.assertEqual(state[collection], [])
        self.assertEqual(state["graph"]["nodes"], [])

    def test_the_opened_session_validates_against_the_session_schema(self) -> None:
        """#226: an unclassified draft request is a valid statement."""
        self.assertEqual(session_violations(self.co.state(self.sid)), [])

    def test_a_statement_past_draft_still_needs_a_role(self) -> None:
        state = self.co.state(self.sid)
        state["statements"][0]["status"] = "approved"
        violations = session_violations(state)
        self.assertEqual(len(violations), 1)
        self.assertIn("$.statements[0]", violations[0])
        self.assertIn("primary_role", violations[0])

    def test_an_empty_request_opens_nothing(self) -> None:
        with self.assertRaises(CommandRefused):
            self.co.open_session(title="", request="   ")


class AdmitClassificationsFromAFramingResult(Fixture):
    """#227."""

    def test_one_classification_emits_one_event_and_leaves_the_text_alone(self) -> None:
        before = len(self.co.history(self.sid))
        self.classify()
        history = self.co.history(self.sid)
        self.assertEqual([e["type"] for e in history[before:]], ["statement.classified"])
        statement = self.co.state(self.sid)["statements"][0]
        self.assertEqual((statement["primary_role"], statement["secondary_roles"]), ("proposal", ["need"]))
        self.assertEqual(statement["text"], REQUEST)
        self.assertEqual(session_violations(self.co.state(self.sid)), [])

    def test_the_commit_carries_the_next_revision_on_its_last_event(self) -> None:
        self.classify()
        self.assertEqual(self.co.history(self.sid)[-1]["revision"], 1)
        self.assertEqual(self.revision(), 1)

    def test_other_proposal_kinds_are_held_not_committed(self) -> None:
        result = self.co.manual_framing_result(self.sid, [])
        result["proposals"].append(
            {
                "id": "prop_frame_001",
                "kind": "problem_frame",
                "operation": "add",
                "value": {"question": "How might we?"},
                "provenance": {"kind": "inferred", "source_ids": ["stmt_001"]},
            }
        )
        out = self.co.admit_result(self.sid, result)
        self.assertEqual((out["outcome"], out["held_proposal_ids"]), ("held", ["prop_frame_001"]))
        self.assertEqual(len(self.co.history(self.sid)), 2)

    def test_a_stale_result_is_held_and_an_impossible_one_refused(self) -> None:
        result = self.co.manual_framing_result(self.sid, [{"statement_id": "stmt_001", "primary_role": "need"}])
        self.co.admit_result(self.sid, copy.deepcopy(result))
        with self.assertRaises(CommandRefused) as stale:
            self.co.admit_result(self.sid, result)
        self.assertEqual(stale.exception.code, "revision_conflict")
        result["input_revision"] = 99
        with self.assertRaises(CommandRefused) as impossible:
            self.co.admit_result(self.sid, result)
        self.assertEqual(impossible.exception.code, "invariant_violation")
        self.assertEqual(len(self.co.history(self.sid)), 3)

    def test_classifying_an_unknown_statement_commits_nothing(self) -> None:
        result = self.co.manual_framing_result(self.sid, [{"statement_id": "stmt_404", "primary_role": "need"}])
        with self.assertRaises(CommandRefused) as refused:
            self.co.admit_result(self.sid, result)
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertEqual(len(self.co.history(self.sid)), 2)

    def test_a_role_outside_the_schema_commits_nothing(self) -> None:
        result = self.co.manual_framing_result(self.sid, [{"statement_id": "stmt_001", "primary_role": "vibe"}])
        with self.assertRaises(CommandRefused) as refused:
            self.co.admit_result(self.sid, result)
        self.assertEqual(refused.exception.code, "schema_invalid")
        self.assertEqual(len(self.co.history(self.sid)), 2)


class CorrectAClassification(Fixture):
    """#228."""

    def test_a_correction_is_one_more_classification_and_the_text_is_intact(self) -> None:
        self.classify("proposal")
        self.co.correct_classification(
            self.sid, statement_id="stmt_001", primary_role="need", secondary_roles=[], expected_revision=1
        )
        classified = [e for e in self.co.history(self.sid) if e["type"] == "statement.classified"]
        self.assertEqual([e["payload"]["primary_role"] for e in classified], ["proposal", "need"])
        statement = self.co.state(self.sid)["statements"][0]
        self.assertEqual((statement["primary_role"], statement["text"]), ("need", REQUEST))

    def test_correcting_a_missing_statement_is_refused(self) -> None:
        self.classify()
        with self.assertRaises(CommandRefused) as refused:
            self.co.correct_classification(
                self.sid, statement_id="stmt_404", primary_role="need", secondary_roles=[], expected_revision=1
            )
        self.assertEqual(refused.exception.code, "invariant_violation")

    def test_a_command_formed_against_an_old_revision_conflicts(self) -> None:
        self.classify()
        with self.assertRaises(CommandRefused) as refused:
            self.co.correct_classification(
                self.sid, statement_id="stmt_001", primary_role="need", secondary_roles=[], expected_revision=0
            )
        self.assertEqual(refused.exception.code, "revision_conflict")

    def test_abstraction_is_required_until_an_outcome_is_present(self) -> None:
        self.classify("proposal")
        self.assertTrue(self.co.view(self.sid)["derived"]["abstraction_required"])
        self.co.add_statement(self.sid, text="Pack cost per usable kWh meets the target.", primary_role="outcome", expected_revision=1)
        self.assertFalse(self.co.view(self.sid)["derived"]["abstraction_required"])


class SealIntakeThroughTheGate(Fixture):
    """#229."""

    def test_an_accepted_gate_appends_its_events_and_moves_to_framing(self) -> None:
        self.classify()
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        statement = self.co.state(self.sid)["statements"][0]
        out = approve(self.co, request)
        state = self.co.state(self.sid)
        self.assertEqual((out["outcome"], state["phase"], state["revision"]), ("accepted", "framing", 2))
        self.assertEqual(state["approvals"][0]["target_digest"], content_digest(statement))
        self.assertEqual([e["type"] for e in self.co.history(self.sid)[-2:]], ["approval.recorded", "phase.changed"])

    def test_a_forged_request_digest_appends_nothing(self) -> None:
        self.classify()
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        forged = dict(request, request_digest="sha256:" + "0" * 64)
        with self.assertRaises(CommandRefused) as refused:
            approve(self.co, forged)
        self.assertEqual(refused.exception.code, "approval_stale")
        self.assertEqual(self.co.state(self.sid)["phase"], "intake")

    def test_content_changed_after_display_appends_nothing(self) -> None:
        self.classify()
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        self.co.correct_classification(self.sid, statement_id="stmt_001", primary_role="need", secondary_roles=[], expected_revision=1)
        with self.assertRaises(CommandRefused) as refused:
            approve(self.co, request)
        self.assertEqual(refused.exception.code, "approval_stale")
        self.assertEqual(self.co.state(self.sid)["phase"], "intake")

    def test_a_rejection_records_nothing(self) -> None:
        self.classify()
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        with self.assertRaises(CommandRefused) as refused:
            approve(self.co, request, "rejected")
        self.assertEqual(refused.exception.code, "approval_required")
        self.assertEqual(self.co.state(self.sid)["approvals"], [])

    def test_a_gate_from_the_wrong_phase_cannot_even_be_prepared(self) -> None:
        with self.assertRaises(CommandRefused) as refused:
            self.co.prepare_gate(self.sid, gate="decision_approval", target_id="stmt_001")
        self.assertEqual(refused.exception.code, "invariant_violation")

    def test_a_role_without_authority_cannot_approve(self) -> None:
        facilitator = coordinator(self.store, {"id": "user_facilitator", "kind": "human", "role": "facilitator"})
        self.seal_intake()
        facilitator.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        facilitator.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        request = facilitator.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001")
        with self.assertRaises(CommandRefused) as refused:
            approve(facilitator, request)
        self.assertEqual(refused.exception.code, "approval_required")
        self.assertEqual(self.co.state(self.sid)["phase"], "framing")


class ApprovalsNameTheirInterface(Fixture):
    """ADR-0022: an approval from the manual GUI is distinguishable in the log."""

    def test_an_approval_records_the_local_manual_profile(self) -> None:
        self.seal_intake()
        recorded = [e for e in self.co.history(self.sid) if e["type"] == "approval.recorded"]
        self.assertEqual(
            [e["payload"]["profile_id"] for e in recorded],
            ["approval-profile-frameshift-manual-gui-local-0.1.0"],
        )
        self.assertEqual(session_violations(self.co.state(self.sid)), [])

    def test_local_and_hosted_runs_are_distinct_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            hosted = manual_coordinator(
                Path(other), OWNER, bind="0.0.0.0", public_hosts=("frameshift.example.org",)
            )
            self.assertNotEqual(hosted._profile["id"], self.co._profile["id"])
            self.assertIn("-hosted-", hosted._profile["id"])

    def test_an_approval_recorded_before_the_field_existed_still_validates(self) -> None:
        self.seal_intake()
        legacy = copy.deepcopy(self.co.state(self.sid))
        for approval in legacy["approvals"]:
            del approval["profile_id"]
        self.assertEqual(session_violations(legacy), [])


class TheShallowJourney(Fixture):
    """#89, as far as the current event vocabulary reaches: intake to solutions."""

    def test_request_to_solutions_folds_to_a_valid_session(self) -> None:
        self.seal_intake()
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        working = self.co.state(self.sid)["frames"][0]
        self.assertEqual((working["status"], working["digest"]), ("working", content_digest(working)))
        approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))
        self.co.add_node(self.sid, node={"type": "hypothesis", "label": "Cell price dominates.", "confidence": "low", "source_ids": ["frame_001"]}, expected_revision=self.revision())
        self.co.add_node(self.sid, node={"type": "evidence", "label": "Quote at volume.", "status": "draft", "extensions": {"collected": False}}, expected_revision=self.revision())
        self.co.add_edge(self.sid, edge={"source": "node_002", "target": "node_001", "type": "tests"}, expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="evidence_sufficiency", target_id="node_001"))
        state = self.co.state(self.sid)
        self.assertEqual(state["phase"], "solutions")
        self.assertEqual(session_violations(state), [])
        self.assertEqual(state["graph"]["nodes"][0]["status"], "proposed")
        self.assertEqual(len(state["approvals"]), 3)

    def test_reactivating_moves_the_working_frame_and_rerecords_both_digests(self) -> None:
        self.seal_intake()
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_frame("How might we cut cell count?"), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_002", expected_revision=self.revision())
        frames = self.co.state(self.sid)["frames"]
        self.assertEqual([f["status"] for f in frames], ["proposed", "working"])
        for frame in frames:
            self.assertEqual(frame["digest"], content_digest(frame))

    def test_an_invalid_frame_commits_nothing(self) -> None:
        self.seal_intake()
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.co.propose_frame(self.sid, frame=dict(_frame(), abstraction_level="galaxy"), expected_revision=self.revision())
        self.assertEqual(refused.exception.code, "schema_invalid")
        self.assertEqual(len(self.co.history(self.sid)), before)

    def test_a_restarted_coordinator_reads_the_same_session(self) -> None:
        self.seal_intake()
        again = coordinator(self.store)
        self.assertEqual(again.state(self.sid), self.co.state(self.sid))
        self.assertEqual([s["id"] for s in again.sessions()], [self.sid])


class TheGuiStaysAtTheBoundary(unittest.TestCase):
    """ADR-0022: the GUI imports contracts and orchestration.api only."""

    def test_gui_imports(self) -> None:
        allowed = {"frameshift.contracts", "frameshift.orchestration.api"}
        offenders = []
        for path in (ROOT / "frameshift" / "gui").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                offenders += [f"{path.name}: {n}" for n in names if n.startswith("frameshift") and n not in allowed]
        self.assertEqual(offenders, [])


def _frame(question: str = "How might we reach the pack cost target without losing range?") -> dict:
    return {
        "question": question,
        "outcome": "Pack cost per usable kWh meets the 2027 target.",
        "abstraction_level": "product",
        "system_boundary": "supply_chain",
        "included": "cell sourcing\npack architecture",
        "excluded": "",
        "success_measures": "USD per usable kWh",
        "constraints": "",
        "assumptions": "",
    }


if __name__ == "__main__":
    unittest.main()
