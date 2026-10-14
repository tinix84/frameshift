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


class OnlyThePersonsWordsAreObserved(Fixture):
    """#256 (ADR-0028): `observed` means the person's words, recorded at their boundary."""

    TEXT = "Pack cost per usable kWh meets the target."

    def add(self, provenance=None) -> dict:
        return self.co.add_statement(
            self.sid, text=self.TEXT, primary_role="outcome", expected_revision=self.revision(), provenance=provenance
        )["state"]["statements"][-1]

    def refused(self, provenance: dict) -> str:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.add(provenance)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused statement writes nothing")
        return refused.exception.code

    def test_the_persons_path_mints_a_fresh_intake_record(self) -> None:
        state = self.co.add_operator_statement(
            self.sid, text=self.TEXT, primary_role="outcome", expected_revision=self.revision()
        )["state"]
        request, typed = state["statements"]
        self.assertEqual(typed["provenance"]["kind"], "observed")
        (source,) = typed["provenance"]["source_ids"]
        self.assertTrue(source.startswith("intake_"))
        self.assertNotEqual(source, request["provenance"]["source_ids"][0], "each arrival is its own record")
        self.assertEqual(session_violations(state), [])

    def test_the_reasoners_path_defaults_to_assumed(self) -> None:
        provenance = self.add()["provenance"]
        self.assertEqual((provenance["kind"], provenance["source_ids"]), ("assumed", []))

    def test_the_reasoner_cannot_declare_observed_even_citing_the_person(self) -> None:
        for sources in ([], ["stmt_001"], ["intake_t0001"]):
            with self.subTest(sources=sources):
                self.assertEqual(self.refused({"kind": "observed", "source_ids": sources}), "invariant_violation")

    def test_a_declared_kind_its_sources_earn_is_stored_as_given(self) -> None:
        for provenance in (
            {"kind": "inferred", "source_ids": ["stmt_001"], "note": "Restates the request."},
            {"kind": "sourced", "source_ids": ["art_datasheet_cell"]},
            {"kind": "unknown", "source_ids": []},
            {"kind": "assumed", "source_ids": []},
        ):
            with self.subTest(kind=provenance["kind"]):
                self.assertEqual(self.add(copy.deepcopy(provenance))["provenance"], provenance)

    def test_an_unearned_kind_is_refused(self) -> None:
        self.assertEqual(self.refused({"kind": "inferred", "source_ids": []}), "invariant_violation")
        self.assertEqual(self.refused({"kind": "sourced", "source_ids": ["stmt_001"]}), "invariant_violation")
        self.assertEqual(self.refused({"kind": "certain", "source_ids": []}), "schema_invalid")

    def test_a_dangling_or_unregistered_citation_is_refused_as_an_invariant(self) -> None:
        for sources in (["stmt_099"], ["madeup_001"], ["art_x", "stmt_099"]):
            with self.subTest(sources=sources):
                self.assertEqual(self.refused({"kind": "inferred", "source_ids": sources}), "invariant_violation")

    def test_only_an_intake_record_a_person_minted_can_be_cited(self) -> None:
        request = self.co.state(self.sid)["statements"][0]["provenance"]["source_ids"][0]
        self.assertEqual(self.refused({"kind": "inferred", "source_ids": ["intake_fabricated"]}), "invariant_violation")
        cited = {"kind": "inferred", "source_ids": [request]}
        self.assertEqual(self.add(copy.deepcopy(cited))["provenance"], cited)

    def test_no_reasoner_facing_boundary_names_the_persons_path(self) -> None:
        """ADR-0028: which commands a boundary exposes carries authority; MCP never offers this one."""
        for path in sorted((ROOT / "frameshift" / "mcp").rglob("*.py")) + sorted((ROOT / "adapters").rglob("*.py")):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("add_operator_statement", path.read_text(encoding="utf-8"))

    def test_a_malformed_provenance_is_refused_not_raised(self) -> None:
        for provenance in (
            "observed",
            {"kind": ["observed"], "source_ids": []},
            {"kind": {"observed": True}, "source_ids": []},
            {"kind": "inferred", "source_ids": "stmt_001"},
            {"kind": "inferred", "source_ids": [1]},
        ):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.refused(provenance), "schema_invalid")


class SealingProposesAndThePersonSupersedes(Fixture):
    """#255 (ADR-0029): sealing intake proposes live classified drafts; the person supersedes."""

    def setUp(self) -> None:
        super().setUp()
        self.classify()
        for text in ("The bar brewed the same bag badly too.", "The bar brewed the same bag well."):
            self.co.add_operator_statement(self.sid, text=text, primary_role="observation", expected_revision=self.revision())

    def supersede(self, statement_id: str, superseded_by: str) -> dict:
        return self.co.supersede_statement(
            self.sid, statement_id=statement_id, superseded_by=superseded_by, expected_revision=self.revision()
        )["state"]

    def refused(self, statement_id, superseded_by) -> CommandRefused:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.supersede(statement_id, superseded_by)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused supersession writes nothing")
        return refused.exception

    def seal(self) -> dict:
        approve(self.co, self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001"))
        return self.co.state(self.sid)

    def test_superseding_keeps_both_statements_and_names_the_replacement(self) -> None:
        before = copy.deepcopy(self.co.state(self.sid)["statements"])
        state = self.supersede("stmt_002", "stmt_003")
        first, second = state["statements"][1], state["statements"][2]
        self.assertEqual((first["status"], first["superseded_by"]), ("superseded", "stmt_003"))
        self.assertEqual(first["text"], before[1]["text"])
        self.assertEqual(second, before[2], "the replacement is untouched")
        self.assertEqual(self.co.history(self.sid)[-1]["type"], "statement.status.changed")
        self.assertEqual(session_violations(state), [])
        self.assertEqual(coordinator(self.store).state(self.sid), state, "a restarted coordinator folds the same")

    def test_each_refusal_writes_nothing(self) -> None:
        self.supersede("stmt_002", "stmt_003")
        for statement_id, superseded_by, naming in (
            ("stmt_099", "stmt_003", "no statement"),
            ("stmt_003", "stmt_099", "no replacement"),
            ("stmt_003", "stmt_003", "cannot supersede itself"),
            ("stmt_002", "stmt_003", "only a live statement"),
            ("stmt_003", "stmt_002", "only a live statement"),
            (["stmt_003"], "stmt_001", "no statement"),
        ):
            with self.subTest(statement_id=statement_id, superseded_by=superseded_by):
                refused = self.refused(statement_id, superseded_by)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)

    def test_sealing_proposes_live_classified_drafts_only(self) -> None:
        self.supersede("stmt_002", "stmt_003")
        sealed = self.seal()
        statuses = {statement["id"]: statement["status"] for statement in sealed["statements"]}
        self.assertEqual(statuses, {"stmt_001": "proposed", "stmt_002": "superseded", "stmt_003": "proposed"})
        self.assertEqual(session_violations(sealed), [])

    def test_an_unclassified_draft_stays_draft_through_the_gate(self) -> None:
        """Past draft a statement must be classified (#226): sealing leaves an unclassified one as it is."""
        sid = self.co.open_session(title="", request="Make the coffee better.")["state"]["id"]
        self.co.add_operator_statement(sid, text="Every cup tastes sour.", primary_role="observation", expected_revision=self.co.state(sid)["revision"])
        approve(self.co, self.co.prepare_gate(sid, gate="intake_correction", target_id="stmt_002"))
        statuses = [(s["id"], s["status"]) for s in self.co.state(sid)["statements"]]
        self.assertEqual(statuses, [("stmt_001", "draft"), ("stmt_002", "proposed")])

    def test_other_gates_change_no_status(self) -> None:
        from frameshift.orchestration.sessions import _sealing_events

        self.assertEqual(_sealing_events(self.co.state(self.sid), "frame_selection"), [])

    def test_an_unclassified_statement_cannot_be_superseded(self) -> None:
        sid = self.co.open_session(title="", request="Make the coffee better.")["state"]["id"]
        self.co.add_operator_statement(sid, text="Every cup tastes sour.", primary_role="observation", expected_revision=self.co.state(sid)["revision"])
        before = len(self.co.history(sid))
        with self.assertRaises(CommandRefused) as refused:
            self.co.supersede_statement(sid, statement_id="stmt_001", superseded_by="stmt_002", expected_revision=self.co.state(sid)["revision"])
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertIn("classify it before superseding it", refused.exception.detail)
        self.assertEqual(len(self.co.history(sid)), before)

    def test_no_gate_binds_a_withdrawn_statement(self) -> None:
        self.supersede("stmt_001", "stmt_002")
        intake = next(gate for gate in self.co.view(self.sid)["derived"]["gates"] if gate["gate"] == "intake_correction")
        self.assertEqual(intake["targets"], ["stmt_002", "stmt_003"])
        with self.assertRaises(CommandRefused) as refused:
            self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertIn("no gate binds it", refused.exception.detail)
        self.assertEqual(self.co.state(self.sid)["phase"], "intake")

    def test_a_superseded_statement_no_longer_counts(self) -> None:
        """abstraction_required reads live statements only: a superseded outcome serves nothing."""
        self.co.add_statement(self.sid, text="Pack cost meets the target.", primary_role="outcome", expected_revision=self.revision())
        self.assertFalse(self.co.view(self.sid)["derived"]["abstraction_required"])
        state = self.supersede("stmt_004", "stmt_003")
        self.assertEqual(state["statements"][3]["status"], "superseded")
        self.assertTrue(self.co.view(self.sid)["derived"]["abstraction_required"])

    def test_superseding_belongs_to_intake_framing_and_causal(self) -> None:
        self.seal()
        self.assertEqual(self.supersede("stmt_002", "stmt_003")["phase"], "framing")
        state = self.co.state(self.sid)
        self.co.state = lambda sid: dict(state, phase="solutions")  # noqa: E731
        with self.assertRaises(CommandRefused) as refused:
            self.co.supersede_statement(self.sid, statement_id="stmt_003", superseded_by="stmt_001", expected_revision=state["revision"])
        del self.co.state
        self.assertIn("'intake' or 'framing' or 'causal'", refused.exception.detail)

    def test_no_reasoner_facing_boundary_names_the_command(self) -> None:
        for path in sorted((ROOT / "frameshift" / "mcp").rglob("*.py")) + sorted((ROOT / "adapters").rglob("*.py")):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("supersede_statement", path.read_text(encoding="utf-8"))


class SealIntakeThroughTheGate(Fixture):
    """#229."""

    def test_an_accepted_gate_appends_its_events_and_moves_to_framing(self) -> None:
        self.classify()
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        statement = self.co.state(self.sid)["statements"][0]
        out = approve(self.co, request)
        state = self.co.state(self.sid)
        self.assertEqual((out["outcome"], state["phase"], state["revision"]), ("accepted", "framing", 2))
        # The approval binds what the person saw; sealing then proposes it in the same commit (ADR-0029).
        self.assertEqual(state["approvals"][0]["target_digest"], content_digest(statement))
        self.assertEqual(
            [e["type"] for e in self.co.history(self.sid)[-3:]],
            ["approval.recorded", "phase.changed", "statement.status.changed"],
        )
        self.assertEqual(state["statements"][0]["status"], "proposed")

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


class WithdrawACandidateFrame(Fixture):
    """#246 (ADR-0030): the person withdraws a candidate, so frame selection cannot dead-end."""

    def setUp(self) -> None:
        super().setUp()
        self.seal_intake()

    def propose(self, count: int) -> None:
        for index in range(count):
            frame = dict(_frame(), outcome=f"Pack cost per usable kWh meets target {index + 1}.")
            self.co.propose_frame(self.sid, frame=frame, expected_revision=self.revision())

    def withdraw(self, frame_id) -> dict:
        return self.co.withdraw_frame(self.sid, frame_id=frame_id, expected_revision=self.revision())["state"]

    def refused(self, frame_id) -> CommandRefused:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.withdraw(frame_id)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused withdrawal writes nothing")
        return refused.exception

    def seal(self, frame_id: str) -> str:
        approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id=frame_id))
        return self.co.state(self.sid)["phase"]

    def test_withdrawing_keeps_the_frame_and_re_records_its_digest(self) -> None:
        self.propose(3)
        before = copy.deepcopy(self.co.state(self.sid)["frames"][1])
        state = self.withdraw("frame_002")
        frame = state["frames"][1]
        self.assertEqual(frame["status"], "rejected")
        self.assertEqual({k: v for k, v in frame.items() if k not in {"status", "digest"}},
                         {k: v for k, v in before.items() if k not in {"status", "digest"}})
        self.assertEqual(frame["digest"], content_digest(frame))
        self.assertNotEqual(frame["digest"], before["digest"])
        self.assertEqual([e["type"] for e in self.co.history(self.sid)[-2:]], ["frame.status.changed", "frame.digest.recorded"])
        self.assertNotIn("frame_002", self.co.view(self.sid)["derived"]["frame_set"]["live"])
        self.assertEqual(session_violations(state), [])
        self.assertEqual(coordinator(self.store).state(self.sid), state, "a restarted coordinator folds the same")

    def test_six_candidates_withdraw_one_then_seal(self) -> None:
        self.propose(6)
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        with self.assertRaises(CommandRefused) as refused:
            self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001")
        self.assertIn("holds 6", refused.exception.detail)
        self.withdraw("frame_006")
        self.assertEqual(self.seal("frame_001"), "causal")

    def test_a_twin_withdraws_then_seals(self) -> None:
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_frame("A twin, worded differently?"), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        self.assertFalse(self.co.view(self.sid)["derived"]["frame_set"]["selectable"])
        self.withdraw("frame_002")
        self.assertEqual(self.seal("frame_001"), "causal")

    def test_the_working_a_missing_and_a_withdrawn_frame_are_refused(self) -> None:
        self.propose(3)
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        self.withdraw("frame_002")
        for frame_id, naming in (
            ("frame_001", "activate another candidate first"),
            ("frame_099", "no frame"),
            ("frame_002", "already rejected"),
            (["frame_003"], "no frame"),
        ):
            with self.subTest(frame_id=frame_id):
                refused = self.refused(frame_id)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)
        self.assertEqual(self.co.state(self.sid)["active_frame_id"], "frame_001")

    def test_withdrawal_is_final(self) -> None:
        self.propose(3)
        self.withdraw("frame_002")
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.co.activate_frame(self.sid, frame_id="frame_002", expected_revision=self.revision())
        self.assertIn("propose it again as a new candidate", refused.exception.detail)
        self.assertEqual(len(self.co.history(self.sid)), before)

    def test_withdrawal_belongs_to_framing(self) -> None:
        self.propose(2)
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        self.seal("frame_001")
        with self.assertRaises(CommandRefused) as refused:
            self.withdraw("frame_002")
        self.assertIn("phase 'framing'", refused.exception.detail)

    def test_no_reasoner_facing_boundary_names_the_command(self) -> None:
        for path in sorted((ROOT / "frameshift" / "mcp").rglob("*.py")) + sorted((ROOT / "adapters").rglob("*.py")):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("withdraw_frame", path.read_text(encoding="utf-8"))


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


class InCausal(Fixture):
    """A session in causal whose statements include one the person typed and one the reasoner added."""

    def to_causal(self) -> None:
        self.classify()
        self.co.add_operator_statement(self.sid, text="The pack misses the cost target.", primary_role="observation", expected_revision=self.revision())
        self.co.add_statement(self.sid, text="Pack cost per usable kWh meets the target.", primary_role="outcome", expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001"))
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))

    def setUp(self) -> None:
        super().setUp()
        self.to_causal()
        statements = self.co.state(self.sid)["statements"]
        self.request_intake = statements[0]["provenance"]["source_ids"][0]
        self.typed, self.reasoned = statements[1]["id"], statements[2]["id"]

    def add(self, provenance: dict, status: str = "proposed") -> dict:
        node = {"type": "observation", "label": "Cost above target.", "status": status, "confidence": "high", "provenance": provenance}
        return self.co.add_node(self.sid, node=node, expected_revision=self.revision())["state"]["graph"]["nodes"][-1]

    def refused(self, provenance: dict) -> str:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.add(provenance)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused node writes nothing")
        self.last_detail = refused.exception.detail
        return refused.exception.code


class ANodeKeepsTheKindItsSourcesEarn(InCausal):
    """#257 (ADR-0026, under ADR-0028's conditions): kind is declared and earned, never rewritten."""

    def test_each_kind_its_sources_earn_is_stored_as_given(self) -> None:
        for provenance in (
            {"kind": "observed", "source_ids": [self.typed], "note": "The person said so."},
            {"kind": "observed", "source_ids": [self.request_intake]},
            {"kind": "sourced", "source_ids": ["art_cell_quote"]},
            {"kind": "inferred", "source_ids": [self.reasoned, "frame_001"]},
            {"kind": "assumed", "source_ids": []},
            {"kind": "unknown", "source_ids": []},
        ):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.add(copy.deepcopy(provenance))["provenance"], provenance)

    def test_each_kind_without_its_sources_is_refused_not_rewritten(self) -> None:
        person = "an observed provenance cites the person"
        for provenance, rule in (
            ({"kind": "observed", "source_ids": []}, person),
            ({"kind": "observed", "source_ids": [self.reasoned]}, person),
            ({"kind": "observed", "source_ids": ["frame_001", "art_cell_quote"]}, person),
            ({"kind": "observed", "source_ids": ["intake_fabricated"]}, "not an intake record"),
            ({"kind": "sourced", "source_ids": [self.typed]}, "referenced artifact"),
            ({"kind": "inferred", "source_ids": []}, "at least one source"),
            ({"kind": "inferred", "source_ids": ["node_099"]}, "does not resolve"),
        ):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.refused(provenance), "invariant_violation")
                self.assertIn(rule, self.last_detail)

    def test_a_legacy_observed_statement_with_no_intake_record_earns_nothing(self) -> None:
        """ADR-0028: a replayed log's reasoner statement marked observed with no source earns nothing."""
        import shutil

        shutil.copy(ROOT / "evals" / "fixtures" / "ladder.events.jsonl", self.store / "sess_ladder_001.events.jsonl")
        sid = "sess_ladder_001"
        legacy = self.co.state(sid)["statements"][1]
        self.assertEqual((legacy["id"], legacy["provenance"]["kind"], legacy["provenance"]["source_ids"]), ("stmt_002", "observed", []))
        revision = lambda: self.co.state(sid)["revision"]  # noqa: E731
        self.co.propose_frame(sid, frame=_frame(), expected_revision=revision())
        self.co.propose_frame(sid, frame=_alternative(), expected_revision=revision())
        self.co.activate_frame(sid, frame_id="frame_001", expected_revision=revision())
        approve(self.co, self.co.prepare_gate(sid, gate="frame_selection", target_id="frame_001"))
        node = {"type": "observation", "label": "Cost above target.", "confidence": "high"}

        def add(sources: list[str]) -> dict:
            provenance = {"kind": "observed", "source_ids": sources}
            return self.co.add_node(sid, node=dict(node, provenance=provenance), expected_revision=revision())

        with self.assertRaises(CommandRefused) as refused:
            add(["stmt_002"])
        self.assertIn("an observed provenance cites the person", refused.exception.detail)
        add(["stmt_001"])
        add(["intake_t0001"])

    def test_an_observed_node_earns_nothing_for_the_next(self) -> None:
        first = self.add({"kind": "observed", "source_ids": [self.typed]})
        self.assertEqual(self.refused({"kind": "observed", "source_ids": [first["id"]]}), "invariant_violation")

    def test_one_source_from_the_person_is_enough(self) -> None:
        """ADR-0026: the sources must *include* the person's words."""
        provenance = {"kind": "observed", "source_ids": [self.reasoned, self.typed]}
        self.assertEqual(self.add(copy.deepcopy(provenance))["provenance"], provenance)

    def test_a_malformed_provenance_is_refused_never_defaulted(self) -> None:
        for provenance in ({}, {"kind": None, "source_ids": []}, False, 0, "", [], "observed"):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.refused(provenance), "schema_invalid")

    def test_provenance_and_top_level_sources_together_are_refused(self) -> None:
        before = len(self.co.history(self.sid))
        node = {"type": "observation", "label": "Cost above target.", "source_ids": ["frame_001"],
                "provenance": {"kind": "inferred", "source_ids": [self.reasoned]}}
        with self.assertRaises(CommandRefused) as refused:
            self.co.add_node(self.sid, node=node, expected_revision=self.revision())
        self.assertEqual(refused.exception.code, "schema_invalid")
        self.assertEqual(len(self.co.history(self.sid)), before)

    def test_kind_never_promotes_status(self) -> None:
        provenance = {"kind": "observed", "source_ids": [self.typed]}
        self.assertEqual(self.add(dict(provenance), status="draft")["status"], "draft")
        self.assertEqual(self.add(dict(provenance))["status"], "proposed")
        with self.assertRaises(CommandRefused):
            self.add(dict(provenance), status="approved")

    def test_a_node_without_provenance_keeps_todays_default(self) -> None:
        node = {"type": "hypothesis", "label": "Cell price dominates.", "confidence": "low", "source_ids": ["frame_001"]}
        added = self.co.add_node(self.sid, node=node, expected_revision=self.revision())["state"]["graph"]["nodes"][-1]
        self.assertEqual(
            added["provenance"],
            {"kind": "assumed", "source_ids": ["frame_001"], "note": "Supplied by the reasoner; not established."},
        )


class AnEdgeKeepsItsProvenanceAndExtensions(InCausal):
    """#258 (ADR-0026, ADR-0028): an edge's declared provenance is earned, never rewritten."""

    def setUp(self) -> None:
        super().setUp()
        for label in ("Cell price dominates.", "Cost above target."):
            self.co.add_node(self.sid, node={"type": "hypothesis", "label": label, "confidence": "low"}, expected_revision=self.revision())
        self.view_gates_before = self.co.view(self.sid)["derived"]["gates"]

    def add_edge(self, **fields) -> dict:
        edge = {"source": "node_001", "target": "node_002", "type": "contributes_to", "confidence": "medium"}
        edge.update(fields)
        return self.co.add_edge(self.sid, edge=edge, expected_revision=self.revision())["state"]["graph"]["edges"][-1]

    def refused_edge(self, **fields) -> str:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.add_edge(**fields)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused edge writes nothing")
        self.last_detail = refused.exception.detail
        return refused.exception.code

    def test_each_kind_its_sources_earn_is_stored_as_given(self) -> None:
        for provenance in (
            {"kind": "observed", "source_ids": [self.typed], "note": "The person said so."},
            {"kind": "sourced", "source_ids": ["art_cell_quote"]},
            {"kind": "inferred", "source_ids": ["node_001", self.reasoned]},
            {"kind": "assumed", "source_ids": []},
        ):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.add_edge(provenance=copy.deepcopy(provenance))["provenance"], provenance)

    def test_each_kind_without_its_sources_is_refused_not_rewritten(self) -> None:
        for provenance in (
            {"kind": "observed", "source_ids": [self.reasoned]},
            {"kind": "observed", "source_ids": ["node_001"]},
            {"kind": "sourced", "source_ids": [self.typed]},
            {"kind": "inferred", "source_ids": []},
            {"kind": "inferred", "source_ids": ["stmt_099"]},
        ):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.refused_edge(provenance=provenance), "invariant_violation")
        for provenance in ({}, False, "observed"):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.refused_edge(provenance=provenance), "schema_invalid")

    def test_extensions_are_stored_as_given_and_must_be_an_object(self) -> None:
        self.assertEqual(self.add_edge(extensions={"layer": "analysed"})["extensions"], {"layer": "analysed"})
        for extensions in ("analysed", ["layer"]):
            with self.subTest(extensions=extensions):
                self.assertEqual(self.refused_edge(extensions=extensions), "schema_invalid")

    def test_a_causes_edge_keeps_its_owner_with_a_declared_provenance(self) -> None:
        provenance = {"kind": "sourced", "source_ids": ["art_cell_quote"]}
        edge = self.add_edge(type="causes", provenance=dict(provenance))
        self.assertEqual((edge["owner"], edge["provenance"]), (OWNER, provenance))

    def test_observed_by_the_intake_record_itself_and_never_a_forged_one(self) -> None:
        provenance = {"kind": "observed", "source_ids": [self.request_intake]}
        self.assertEqual(self.add_edge(provenance=dict(provenance))["provenance"], provenance)
        self.assertEqual(self.refused_edge(provenance={"kind": "observed", "source_ids": ["intake_deadbeef"]}), "invariant_violation")
        self.assertIn("not an intake record", self.last_detail)

    def test_extensions_cannot_reach_owner_or_status(self) -> None:
        # A top-level `status` is refused (#259); here only `owner` and `extensions` try.
        edge = self.add_edge(type="causes", owner={"id": "user_evil", "kind": "human"},
                             extensions={"owner": "evil", "status": "approved"})
        self.assertEqual((edge["owner"], edge["status"]), (OWNER, "proposed"))
        self.assertEqual(edge["extensions"], {"owner": "evil", "status": "approved"})

    def test_empty_or_absent_extensions_and_a_copy_of_what_was_given(self) -> None:
        self.assertNotIn("extensions", self.add_edge(extensions=None))
        self.assertEqual(self.add_edge(extensions={})["extensions"], {})
        self.assertEqual(self.refused_edge(extensions=False), "schema_invalid")
        given = {"layer": {"name": "analysed"}}
        provenance = {"kind": "sourced", "source_ids": ["art_cell_quote"]}
        stored = self.add_edge(extensions=given, provenance=provenance)
        given["layer"]["name"] = "changed"
        provenance["source_ids"].append("art_other")
        held = self.co.state(self.sid)["graph"]["edges"][-1]
        self.assertEqual((held["extensions"], held["provenance"]["source_ids"]), ({"layer": {"name": "analysed"}}, ["art_cell_quote"]))
        self.assertEqual(stored["id"], held["id"])

    def test_an_edge_is_offered_as_draft_or_proposed_never_decided(self) -> None:
        """#259: as for a node (#254); a decided status is a person's, reached through a gate."""
        self.assertEqual(self.add_edge()["status"], "proposed")
        self.assertEqual(self.add_edge(status="draft")["status"], "draft")
        for status in ("approved", "rejected", "superseded", "archived", "established", "", None, ["draft"], {"draft": 1}):
            with self.subTest(status=status):
                self.assertEqual(self.refused_edge(status=status), "invariant_violation")
                self.assertIn("a reasoner offers an edge as draft or proposed", self.last_detail)

    def test_a_draft_edge_counts_in_no_gate(self) -> None:
        """#259: no gate reads an edge's status; evidence_sufficiency targets hypothesis nodes only.

        A draft edge into a proposed hypothesis neither adds a target nor can be one.
        """
        edge = self.add_edge(status="draft")
        self.assertEqual(self.co.view(self.sid)["derived"]["gates"], self.view_gates_before)
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.co.prepare_gate(self.sid, gate="evidence_sufficiency", target_id=edge["id"])
        self.assertEqual(refused.exception.code, "invariant_violation")
        self.assertEqual(len(self.co.history(self.sid)), before)
        request = self.co.prepare_gate(self.sid, gate="evidence_sufficiency", target_id=edge["target"])
        self.assertEqual(request["target_id"], edge["target"], "the hypothesis is the target, draft edge or not")
        self.co.cancel(request["id"])

    def test_an_edge_without_provenance_keeps_todays_default(self) -> None:
        edge = self.add_edge()
        self.assertEqual(edge["provenance"], {"kind": "assumed", "source_ids": ["node_001", "node_002"]})
        self.assertNotIn("extensions", edge)


class RecordASymptomSpecification(Fixture):
    """#260 (ADR-0027): the IS / IS NOT specification is a session object."""

    def setUp(self) -> None:
        super().setUp()
        self.classify()
        for text in ("Cost per kWh is 30 % over target.", "The 2025 pack met its target with the same supplier."):
            self.co.add_operator_statement(self.sid, text=text, primary_role="observation", expected_revision=self.revision())

    def spec(self, **changes) -> dict:
        spec = {
            "object": "the 2026 pack",
            "deviation": "cost per usable kWh above target",
            "rows": [
                {"dimension": "what", "is": ["stmt_002"], "is_not": ["stmt_003"], "distinction": "This year's pack only."},
                {"dimension": "when", "is": ["stmt_002"], "is_not": [], "distinction": "Since the cell change.", "needs_more_data": True},
            ],
            "reference": {"measure": "cost per usable kWh", "expected": "at target", "source_ids": ["art_cost_model"]},
            "actual": {"value": "30 % over", "source_ids": ["stmt_002"]},
            "method_source_ids": ["art_kt_pa_guide"],
        }
        spec.update(changes)
        return spec

    def record(self, spec: dict, spec_id: str | None = None) -> dict:
        return self.co.record_symptom_specification(
            self.sid, specification=spec, expected_revision=self.revision(), spec_id=spec_id
        )["state"]

    def refused(self, spec: dict, spec_id: str | None = None) -> CommandRefused:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            self.record(spec, spec_id)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused specification writes nothing")
        return refused.exception

    def test_a_partial_specification_is_one_event_in_intake_and_validates(self) -> None:
        before = len(self.co.history(self.sid))
        state = self.record(self.spec())
        self.assertEqual(len(self.co.history(self.sid)), before + 1)
        self.assertEqual(self.co.history(self.sid)[-1]["type"], "symptom.specification.recorded")
        (recorded,) = state["symptom_specifications"]
        self.assertEqual(recorded, dict(self.spec(), id="spec_001"))
        self.assertEqual(session_violations(state), [])

    def test_recording_again_replaces_it_whole_and_keeps_both_recordings(self) -> None:
        self.record(self.spec())
        rows = self.spec()["rows"] + [{"dimension": "where", "is": ["stmt_002"], "is_not": ["stmt_003"], "distinction": "This line only."}]
        state = self.record(self.spec(rows=rows, actual={"value": "31 % over", "source_ids": ["stmt_002"]}), "spec_001")
        (recorded,) = state["symptom_specifications"]
        self.assertEqual((len(recorded["rows"]), recorded["actual"]["value"]), (3, "31 % over"))
        kinds = [event["type"] for event in self.co.history(self.sid)]
        self.assertEqual(kinds.count("symptom.specification.recorded"), 2)
        self.assertEqual(coordinator(self.store).state(self.sid), state, "a restarted coordinator folds the same")

    def test_re_recording_a_specification_that_does_not_exist_is_refused(self) -> None:
        self.assertEqual(self.refused(self.spec(), "spec_009").code, "invariant_violation")

    def test_a_dangling_id_is_refused_as_an_invariant(self) -> None:
        for spec, naming in (
            (self.spec(rows=[{"dimension": "what", "is": ["stmt_099"], "is_not": [], "distinction": "x"}]), "stmt_099"),
            (self.spec(rows=[{"dimension": "what", "is": [], "is_not": ["intake_t0001"], "distinction": "x"}]), "not a statement"),
            (self.spec(knot_node_id="node_001"), "not a node"),
            (self.spec(actual={"value": "x", "source_ids": ["stmt_099"]}), "does not resolve"),
            (self.spec(reference={"measure": "m", "expected": "e", "source_ids": ["madeup_1"]}), "registered"),
            (self.spec(method_source_ids=["stmt_002"]), "referenced artifact"),
        ):
            with self.subTest(naming=naming):
                refused = self.refused(spec)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)

    def test_an_existing_id_that_is_not_a_statement_is_refused_in_a_row(self) -> None:
        self.record(self.spec())
        row = {"dimension": "what", "is": ["stmt_002"], "is_not": ["spec_001"], "distinction": "x"}
        refused = self.refused(self.spec(rows=[row]))
        self.assertEqual(refused.code, "invariant_violation")
        self.assertIn("spec_001", refused.detail)

    def test_re_recording_keeps_the_specification_in_its_place(self) -> None:
        self.record(self.spec())
        self.record(self.spec(deviation="weight per pack above target"))
        state = self.record(self.spec(object="the 2026 pack, line B"), "spec_001")
        self.assertEqual([item["id"] for item in state["symptom_specifications"]], ["spec_001", "spec_002"])
        self.assertEqual(state["symptom_specifications"][0]["object"], "the 2026 pack, line B")

    def test_a_schema_refusal_names_the_place_the_specification_holds(self) -> None:
        self.record(self.spec())
        self.record(self.spec(deviation="weight per pack above target"))
        refused = self.refused(self.spec(object=""), "spec_001")
        self.assertEqual(refused.code, "schema_invalid")
        self.assertIn("$.symptom_specifications[0].object", refused.detail)

    def test_an_unknown_field_is_refused_not_dropped(self) -> None:
        for spec in (dict(self.spec(), notes="x"), dict(self.spec(), id="spec_001")):
            with self.subTest(keys=sorted(set(spec) - set(self.spec()))):
                self.assertEqual(self.refused(spec).code, "schema_invalid")

    def test_a_spec_id_that_is_not_a_string_is_refused(self) -> None:
        self.record(self.spec())
        for spec_id in (["spec_001"], {}, 1):
            with self.subTest(spec_id=spec_id):
                self.assertEqual(self.refused(self.spec(), spec_id).code, "invariant_violation")

    def test_a_specification_cannot_cite_itself(self) -> None:
        self.record(self.spec())
        for spec in (
            self.spec(provenance={"kind": "inferred", "source_ids": ["spec_001"]}),
            self.spec(actual={"value": "x", "source_ids": ["spec_001"]}),
        ):
            with self.subTest(spec=spec):
                refused = self.refused(spec, "spec_001")
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn("cannot cite itself", refused.detail)

    def test_the_command_belongs_to_intake_framing_and_causal_only(self) -> None:
        state = self.co.state(self.sid)
        for phase in ("solutions", "decision", "monitoring"):
            with self.subTest(phase=phase):
                self.co.state = lambda sid, phase=phase: dict(state, phase=phase)  # noqa: E731
                with self.assertRaises(CommandRefused) as refused:
                    self.co.record_symptom_specification(self.sid, specification=self.spec(), expected_revision=state["revision"])
                self.assertEqual(refused.exception.code, "invariant_violation")
                self.assertIn("'intake' or 'framing' or 'causal'", refused.exception.detail)
        del self.co.state
        self.assertEqual(self.co.state(self.sid)["revision"], state["revision"], "nothing was written")

    def test_two_rows_for_one_dimension_are_refused(self) -> None:
        row = {"dimension": "what", "is": ["stmt_002"], "is_not": [], "distinction": "x"}
        refused = self.refused(self.spec(rows=[row, dict(row)]))
        self.assertEqual(refused.code, "invariant_violation")
        self.assertIn("repeats dimension 'what'", refused.detail)

    def test_a_malformed_specification_is_a_schema_matter(self) -> None:
        for spec in (
            "a deviation",
            self.spec(deviation=""),
            self.spec(rows="what"),
            self.spec(rows=[{"dimension": "why", "is": [], "is_not": [], "distinction": "x"}]),
            self.spec(rows=[{"dimension": "what", "is": "stmt_002", "is_not": [], "distinction": "x"}]),
            {k: v for k, v in self.spec().items() if k != "object"},
        ):
            with self.subTest(spec=spec):
                self.assertEqual(self.refused(spec).code, "schema_invalid")

    def test_a_declared_provenance_must_be_earned(self) -> None:
        observed = {"kind": "observed", "source_ids": ["stmt_002"]}
        self.assertEqual(self.record(self.spec(provenance=observed))["symptom_specifications"][0]["provenance"], observed)
        refused = self.refused(self.spec(provenance={"kind": "sourced", "source_ids": ["stmt_002"]}))
        self.assertEqual(refused.code, "invariant_violation")

    def test_the_knot_node_is_named_once_the_graph_exists(self) -> None:
        self.record(self.spec())
        approve(self.co, self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001"))
        self.co.propose_frame(self.sid, frame=_frame(), expected_revision=self.revision())
        self.co.propose_frame(self.sid, frame=_alternative(), expected_revision=self.revision())
        self.co.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        approve(self.co, self.co.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))
        self.co.add_node(self.sid, node={"type": "observation", "label": "Cost above target.", "confidence": "high"}, expected_revision=self.revision())
        state = self.record(self.spec(knot_node_id="node_001"), "spec_001")
        self.assertEqual(state["symptom_specifications"][0]["knot_node_id"], "node_001")
        self.assertEqual(session_violations(state), [])


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
