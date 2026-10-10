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
        facilitator.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
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


def _rung(level: str = "product", loss: str = "Cell chemistry choices drop out of view.") -> dict:
    return {
        "abstraction_level": level,
        "outcome": "Pack cost per usable kWh meets the 2027 target.",
        "scope": "The pack as sold, across its service life.",
        "system_boundary": "product",
        "success_measures": ["cost per usable kWh"],
        "assumptions": ["the 2027 volume step holds"],
        "loss": loss,
        "provenance": {"kind": "inferred", "source_ids": ["stmt_001"]},
    }


class RecordTheLadder(Fixture):
    """#237 (ADR-0024)."""

    def test_a_rung_is_one_event_in_framing_and_validates(self) -> None:
        self.seal_intake()
        before = len(self.co.history(self.sid))
        self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        history = self.co.history(self.sid)
        self.assertEqual([e["type"] for e in history[before:]], ["ladder.rung.recorded"])
        state = self.co.state(self.sid)
        self.assertEqual(state["ladder"][0]["id"], "rung_001")
        self.assertEqual(session_violations(state), [])

    def test_a_rung_is_refused_outside_framing(self) -> None:
        with self.assertRaises(CommandRefused) as refused:
            self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertNotIn("ladder", self.co.state(self.sid))

    def test_re_recording_replaces_the_rung_and_keeps_both_recordings(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        self.co.record_rung(self.sid, rung=_rung(loss="Supplier options drop out of view."), rung_id="rung_001", expected_revision=self.revision())
        state = self.co.state(self.sid)
        self.assertEqual([r["loss"] for r in state["ladder"]], ["Supplier options drop out of view."])
        recorded = [e for e in self.co.history(self.sid) if e["type"] == "ladder.rung.recorded"]
        self.assertEqual(len(recorded), 2)

    def test_re_recording_a_rung_that_does_not_exist_is_refused(self) -> None:
        self.seal_intake()
        with self.assertRaises(CommandRefused):
            self.co.record_rung(self.sid, rung=_rung(), rung_id="rung_404", expected_revision=self.revision())

    def test_a_second_rung_at_an_occupied_level_commits_nothing(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        self.assertEqual(refused.exception.code, "schema_invalid")
        self.assertIn("already holds", refused.exception.detail)
        self.assertEqual(len(self.co.history(self.sid)), before)

    def test_a_rung_without_its_loss_commits_nothing(self) -> None:
        self.seal_intake()
        with self.assertRaises(CommandRefused):
            self.co.record_rung(self.sid, rung=dict(_rung(), loss=""), expected_revision=self.revision())

    def test_a_rung_citing_a_missing_statement_commits_nothing(self) -> None:
        self.seal_intake()
        rung = dict(_rung(), provenance={"kind": "inferred", "source_ids": ["stmt_999"]})
        with self.assertRaises(CommandRefused):
            self.co.record_rung(self.sid, rung=rung, expected_revision=self.revision())

    def test_the_view_orders_the_ladder_by_level_not_by_recording(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung("business"), expected_revision=self.revision())
        self.co.record_rung(self.sid, rung=_rung("component"), expected_revision=self.revision())
        self.co.record_rung(self.sid, rung=_rung("product"), expected_revision=self.revision())
        self.assertEqual(self.co.view(self.sid)["derived"]["ladder_order"], ["rung_002", "rung_003", "rung_001"])

    def test_a_restarted_coordinator_folds_the_same_ladder(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung(), expected_revision=self.revision())
        self.assertEqual(coordinator(self.store).state(self.sid)["ladder"], self.co.state(self.sid)["ladder"])


class TheShallowJourney(Fixture):
    """#89, as far as the current event vocabulary reaches: intake to solutions."""

    def test_request_to_solutions_folds_to_a_valid_session(self) -> None:
        self.seal_intake()
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
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

    def test_a_reasoner_cannot_offer_a_node_with_a_decided_status(self) -> None:
        """#254: approved, rejected, superseded and archived are decisions, never fields."""
        self.seal_intake()
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))
        before = len(self.co.history(self.sid))
        for status in ("approved", "rejected", "superseded", "archived", "established", ""):
            with self.subTest(status=status), self.assertRaises(CommandRefused) as refused:
                self.co.add_node(
                    self.sid,
                    node={"type": "hypothesis", "label": "Scale insulates the thermoblock.", "status": status, "confidence": "high"},
                    expected_revision=self.revision(),
                )
            self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused node writes nothing")
        for status in ("draft", "proposed"):
            self.co.add_node(self.sid, node={"type": "hypothesis", "label": f"Offered {status}.", "status": status}, expected_revision=self.revision())
        self.co.add_node(self.sid, node={"type": "hypothesis", "label": "No status given."}, expected_revision=self.revision())
        self.assertEqual([n["status"] for n in self.co.state(self.sid)["graph"]["nodes"]], ["draft", "proposed", "proposed"])

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


def _alternative() -> dict:
    """A second candidate that differs from `_frame()` on boundary and level."""
    return dict(
        _frame("How might we lower the cost of a usable kWh across the pack's whole life?"),
        abstraction_level="business",
        system_boundary="lifecycle",
    )


HELD = [
    {
        "id": "prop_ladder_001",
        "kind": "abstraction_ladder",
        "operation": "add",
        "value": {"levels": ["business", "component", "product"], "top_outcome": "Improve contribution margin per pack."},
        "provenance": {"kind": "inferred", "source_ids": ["stmt_001"]},
    },
    {
        "id": "prop_frame_001",
        "kind": "problem_frame",
        "operation": "add",
        "value": {"question": "How might we improve contribution margin per pack?", "abstraction_level": "business", "status": "proposed"},
        "provenance": {"kind": "inferred", "source_ids": ["stmt_001"]},
    },
]


class KeepAndAdoptHeldProposals(Fixture):
    """#238 (ADR-0024)."""

    def classify(self, role: str = "proposal", secondary=("need",)) -> dict:
        result = self.co.manual_framing_result(
            self.sid, [{"statement_id": "stmt_001", "primary_role": role, "secondary_roles": list(secondary)}]
        )
        result["proposals"].extend(copy.deepcopy(HELD))
        return self.co.admit_result(self.sid, result)

    def test_admission_commits_only_classifications_and_holds_the_rest(self) -> None:
        before = len(self.co.history(self.sid))
        outcome = self.classify()
        self.assertEqual(outcome["held_proposal_ids"], ["prop_ladder_001", "prop_frame_001"])
        self.assertEqual([e["type"] for e in self.co.history(self.sid)[before:]], ["statement.classified"])
        held = self.co.view(self.sid)["derived"]["held"]
        self.assertEqual(sorted(held["by_kind"]), ["abstraction_ladder", "problem_frame"])
        self.assertFalse(held["stale"])

    def test_a_later_commit_marks_the_held_result_stale_and_keeps_it(self) -> None:
        self.seal_intake()
        held = self.co.view(self.sid)["derived"]["held"]
        self.assertTrue(held["stale"])
        self.assertEqual(len(held["by_kind"]["problem_frame"]), 1)

    def test_a_held_frame_is_adopted_through_propose_frame_after_editing(self) -> None:
        self.seal_intake()
        draft = self.co.held_draft(self.sid, proposal_id="prop_frame_001")
        self.assertEqual(draft["command"], "propose_frame")
        self.assertEqual(draft["frame"]["question"], "How might we improve contribution margin per pack?")
        self.assertNotIn("status", draft["frame"])
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused):
            self.co.propose_frame(self.sid, frame=draft["frame"], expected_revision=self.revision())
        self.assertEqual(len(self.co.history(self.sid)), before)
        edited = dict(draft["frame"], outcome="Contribution margin per pack rises.", system_boundary="business_model")
        self.co.propose_frame(self.sid, frame=edited, expected_revision=self.revision())
        frame = self.co.state(self.sid)["frames"][0]
        self.assertEqual((frame["status"], frame["abstraction_level"]), ("proposed", "business"))

    def test_a_held_ladder_drafts_one_rung_per_level_in_order(self) -> None:
        self.seal_intake()
        draft = self.co.held_draft(self.sid, proposal_id="prop_ladder_001")
        self.assertEqual(draft["command"], "record_rung")
        self.assertEqual([r["abstraction_level"] for r in draft["rungs"]], ["component", "product", "business"])
        self.assertEqual([r["outcome"] for r in draft["rungs"]], ["", "", "Improve contribution margin per pack."])
        top = dict(draft["rungs"][2], scope="The business the pack serves.", system_boundary="business_model", loss="Pack engineering detail drops out of view.")
        self.co.record_rung(self.sid, rung=top, expected_revision=self.revision())
        rung = self.co.state(self.sid)["ladder"][0]
        self.assertEqual(rung["provenance"]["source_ids"], ["stmt_001"])
        self.assertIn("prop_ladder_001", rung["provenance"]["note"])
        self.assertEqual(session_violations(self.co.state(self.sid)), [])

    def test_a_later_classification_holding_nothing_keeps_the_held_result(self) -> None:
        self.classify()
        self.co.add_statement(self.sid, text="Pack cost per usable kWh meets the target.", primary_role="outcome", expected_revision=self.revision())
        manual = self.co.manual_framing_result(self.sid, [{"statement_id": "stmt_002", "primary_role": "outcome", "secondary_roles": []}])
        self.assertEqual(self.co.admit_result(self.sid, manual)["outcome"], "admitted")
        held = self.co.view(self.sid)["derived"]["held"]
        self.assertEqual(sorted(held["by_kind"]), ["abstraction_ladder", "problem_frame"])
        self.co.held_draft(self.sid, proposal_id="prop_frame_001")

    def test_a_ladder_draft_re_records_a_level_already_on_the_ladder(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung("product"), expected_revision=self.revision())
        rungs = self.co.held_draft(self.sid, proposal_id="prop_ladder_001")["rungs"]
        self.assertEqual([r["rung_id"] for r in rungs], [None, "rung_001", None])
        # Seeded from the recorded rung, since a re-recording replaces it whole.
        recorded = self.co.state(self.sid)["ladder"][0]
        self.assertEqual({k: v for k, v in rungs[1].items() if k != "rung_id"}, {k: v for k, v in recorded.items() if k != "id"})
        edited = dict(rungs[1], outcome="Pack margin holds.", scope="The pack as sold.", system_boundary="product", loss="Cells drop out of view.")
        self.co.record_rung(self.sid, rung=edited, rung_id=rungs[1]["rung_id"], expected_revision=self.revision())
        self.assertEqual(len(self.co.state(self.sid)["ladder"]), 1)

    def test_a_top_level_already_on_the_ladder_takes_only_the_proposed_outcome(self) -> None:
        self.seal_intake()
        self.co.record_rung(self.sid, rung=_rung("business"), expected_revision=self.revision())
        top = self.co.held_draft(self.sid, proposal_id="prop_ladder_001")["rungs"][-1]
        self.assertEqual(top["rung_id"], "rung_001")
        self.assertEqual(top["outcome"], "Improve contribution margin per pack.")
        self.assertEqual((top["scope"], top["loss"], top["assumptions"]), (_rung()["scope"], _rung()["loss"], _rung()["assumptions"]))
        self.assertIn("prop_ladder_001", top["provenance"]["note"])
        self.co.record_rung(self.sid, rung=top, rung_id=top["rung_id"], expected_revision=self.revision())
        self.assertEqual(session_violations(self.co.state(self.sid)), [])

    def test_a_malformed_held_value_drafts_what_it_can_and_never_raises(self) -> None:
        odd = [
            dict(HELD[0], id="prop_ladder_002", value={"levels": [{"name": "system"}, "system", "system", 7], "top_outcome": ["x"]},
                 provenance={"kind": "assumed", "source_ids": ["stmt_001"]}),
            dict(HELD[0], id="prop_ladder_003", value={"levels": 7}),
        ]
        result = self.co.manual_framing_result(self.sid, [{"statement_id": "stmt_001", "primary_role": "proposal", "secondary_roles": ["need"]}])
        result["proposals"].extend(copy.deepcopy(odd))
        self.co.admit_result(self.sid, result)
        rungs = self.co.held_draft(self.sid, proposal_id="prop_ladder_002")["rungs"]
        self.assertEqual([(r["abstraction_level"], r["outcome"]) for r in rungs], [("system", "")])
        self.assertEqual(rungs[0]["provenance"]["kind"], "assumed")
        self.assertEqual(rungs[0]["provenance"]["source_ids"], ["stmt_001"])
        self.assertEqual(self.co.held_draft(self.sid, proposal_id="prop_ladder_003")["rungs"], [])

    def test_drafting_writes_nothing(self) -> None:
        self.seal_intake()
        before = self.co.history(self.sid)
        self.co.held_draft(self.sid, proposal_id="prop_frame_001")
        self.co.held_draft(self.sid, proposal_id="prop_ladder_001")
        self.assertEqual(self.co.history(self.sid), before)

    def test_an_unknown_proposal_is_refused(self) -> None:
        self.classify()
        with self.assertRaises(CommandRefused):
            self.co.held_draft(self.sid, proposal_id="prop_absent")

    def test_a_restarted_coordinator_holds_nothing_and_says_so(self) -> None:
        self.classify()
        held = coordinator(self.store).view(self.sid)["derived"]["held"]
        self.assertEqual(held["by_kind"], {})
        self.assertIn("restart", held["note"])
        with self.assertRaises(CommandRefused):
            coordinator(self.store).held_draft(self.sid, proposal_id="prop_frame_001")


class GateFrameSelection(Fixture):
    """#239 (ADR-0024)."""

    def framing(self, *frames: dict) -> None:
        self.seal_intake()
        for frame in frames:
            self.co.propose_frame(self.sid, frame=frame, expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())

    def refused(self) -> CommandRefused:
        with self.assertRaises(CommandRefused) as refused:
            self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001")
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertEqual(self.co.state(self.sid)["phase"], "framing")
        return refused.exception

    def test_one_candidate_is_refused(self) -> None:
        self.framing(_frame())
        self.assertIn("holds 1 (frame_001)", self.refused().detail)

    def test_six_candidates_are_refused(self) -> None:
        levels = ("component", "subsystem", "system", "product", "business", "business")
        boundaries = ("component", "subsystem", "product", "operations", "portfolio", "business_model")
        self.framing(*[dict(_frame(), abstraction_level=l, system_boundary=b) for l, b in zip(levels, boundaries)])
        self.assertIn("holds 6", self.refused().detail)

    def test_two_candidates_agreeing_on_all_three_axes_are_refused(self) -> None:
        twin = dict(_frame("A different question, same frame."), outcome="  PACK COST per usable kWh meets the 2027 target. ")
        self.framing(_frame(), twin)
        detail = self.refused().detail
        self.assertIn("frame_001 and frame_002", detail)
        self.assertEqual(self.co.view(self.sid)["derived"]["frame_set"]["indistinct_pairs"], [["frame_001", "frame_002"]])

    def test_differing_on_one_axis_is_enough(self) -> None:
        for change in ({"outcome": "Range at end of life is kept."}, {"abstraction_level": "system"}, {"system_boundary": "operations"}):
            with self.subTest(change=change):
                self.tearDown(); self.setUp()
                self.framing(_frame(), dict(_frame(), **change))
                self.assertTrue(self.co.view(self.sid)["derived"]["frame_set"]["selectable"])
                approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))
                self.assertEqual(self.co.state(self.sid)["phase"], "causal")

    def test_rejected_and_superseded_frames_do_not_count(self) -> None:
        self.framing(_frame(), _alternative())
        state = self.co.state(self.sid)
        state["frames"][1]["status"] = "rejected"
        from frameshift.orchestration.sessions import frame_set

        self.assertEqual(frame_set(state)["live"], ["frame_001"])
        self.assertFalse(frame_set(state)["selectable"])

    def test_a_frame_added_after_preparing_is_checked_again_on_confirm(self) -> None:
        self.framing(_frame(), _alternative())
        request = self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001")
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        with self.assertRaises(CommandRefused) as refused:
            approve(self.co, request)
        self.assertIn("frame_001 and frame_003", refused.exception.detail)
        self.assertEqual(self.co.state(self.sid)["phase"], "framing")

    def test_the_reference_history_still_folds(self) -> None:
        from frameshift.orchestration import replay

        events = [json.loads(line) for line in (ROOT / "evals" / "fixtures" / "reference.events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        reference = json.loads((ROOT / "evals" / "fixtures" / "reference.checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(replay.fold(events), reference["state"])


if __name__ == "__main__":
    unittest.main()
