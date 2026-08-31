#!/usr/bin/env python3
"""Tests that the approval fixtures would fail if a gate were loosened.

Negative cases outnumber positive ones by design — the value is in what gets
refused — so the risk is a check that refuses everything and proves nothing.
These tests hold both ends: the accepted attempts really are accepted, and each
refusal really is caused by the thing the case names.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import approval, schema  # noqa: E402

SESSION = "evals/fixtures/approval/gates.session.json"
ACCEPTED_CASE = "evals/fixtures/approval-gates-accept-a-bound-approval.case.json"
REFUSALS_CASE = "evals/fixtures/approval-refusals.case.json"


def transition(gate: str, target_id: str) -> dict:
    return {"gate": gate, "target_id": target_id, "to_phase": "causal"}


class GateCoverageTests(unittest.TestCase):
    def test_the_gates_are_the_eight_in_the_contract(self) -> None:
        """`GATE_AUTHORITY` mirrors the checkpoint gates the schemas publish."""
        engine_result = schema.load_schema("engine-result.schema.json")
        published = set(engine_result["properties"]["required_checkpoints"]["items"]["enum"])
        self.assertEqual(published, set(approval.GATE_AUTHORITY))

    def test_every_gate_has_an_accepted_attempt(self) -> None:
        case = run.load(ACCEPTED_CASE)
        self.assertEqual(run.evaluate(case), [])
        covered = {attempt["gate"] for attempt in case["attempts"] if attempt["expect"]["outcome"] == "accepted"}
        self.assertEqual(covered, set(approval.GATE_AUTHORITY))

    def test_a_missing_gate_fails_the_coverage_expectation(self) -> None:
        case = run.load(ACCEPTED_CASE)
        case["attempts"] = [item for item in case["attempts"] if item["gate"] != "external_action"]
        errors = run.evaluate(case)
        self.assertTrue(any("external_action" in error for error in errors), errors)


class SessionFixtureTests(unittest.TestCase):
    def test_the_starting_state_is_schema_valid(self) -> None:
        session = run.load(SESSION)
        errors = schema.validate(session, schema.load_schema("session.schema.json"), current="session.schema.json")
        self.assertEqual(errors, [])

    def test_the_frame_digest_matches_its_content(self) -> None:
        session = run.load(SESSION)
        frame = session["frames"][0]
        self.assertEqual(frame["digest"], approval.content_digest(frame))


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = run.load(SESSION)

    def bound(self, gate: str = "frame_selection", target_id: str = "frame_001") -> dict:
        actor = {"id": "user_lead_eng", "kind": "human", "role": sorted(approval.GATE_AUTHORITY[gate])[0]}
        return approval.bind_approval(self.session, gate, target_id, actor)

    def test_a_correctly_bound_approval_advances_the_phase(self) -> None:
        result = approval.attempt_transition(self.session, transition("frame_selection", "frame_001"), self.bound())
        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(result["phase"], "causal")

    def test_a_refused_transition_leaves_the_phase_alone(self) -> None:
        result = approval.attempt_transition(self.session, transition("frame_selection", "frame_001"), None)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["phase"], self.session["phase"])

    def test_editing_the_target_invalidates_the_approval_bound_to_it(self) -> None:
        signed = self.bound()
        approval.apply_edit(self.session, {"target_id": "frame_001", "field": "outcome", "value": "Something else."})
        signed["session_revision"] = self.session["revision"]  # isolate the digest
        result = approval.attempt_transition(self.session, transition("frame_selection", "frame_001"), signed)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["code"], approval.APPROVAL_STALE)
        self.assertIn("target_digest", result["detail"])

    def test_re_approving_after_an_edit_is_accepted(self) -> None:
        approval.apply_edit(self.session, {"target_id": "frame_001", "field": "outcome", "value": "Something else."})
        result = approval.attempt_transition(self.session, transition("frame_selection", "frame_001"), self.bound())
        self.assertEqual(result["outcome"], "accepted")

    def test_no_role_can_pass_every_gate(self) -> None:
        """Authority is per gate; a single role must not be a master key."""
        roles = set().union(*approval.GATE_AUTHORITY.values())
        for role in roles:
            passable = {gate for gate, allowed in approval.GATE_AUTHORITY.items() if role in allowed}
            self.assertNotEqual(passable, set(approval.GATE_AUTHORITY), role)

    def test_an_unknown_gate_is_refused(self) -> None:
        result = approval.attempt_transition(self.session, transition("ship_it", "frame_001"), self.bound())
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["code"], approval.INVARIANT_VIOLATION)


class RefusalCaseTests(unittest.TestCase):
    def test_every_refusal_names_a_published_error_code(self) -> None:
        published = {approval.APPROVAL_REQUIRED, approval.APPROVAL_STALE, approval.INVARIANT_VIOLATION}
        case = run.load(REFUSALS_CASE)
        for attempt in case["attempts"]:
            self.assertIn(attempt["expect"]["violation"], published, attempt["id"])

    def test_each_refusal_case_is_caused_by_what_it_names(self) -> None:
        """Flip the expected code on each attempt; every one must then fail."""
        case = run.load(REFUSALS_CASE)
        for index, attempt in enumerate(case["attempts"]):
            mutated = copy.deepcopy(case)
            other = "approval_stale" if attempt["expect"]["violation"] != "approval_stale" else "approval_required"
            mutated["attempts"] = [mutated["attempts"][index]]
            mutated["attempts"][0]["expect"]["violation"] = other
            self.assertTrue(run.evaluate(mutated), attempt["id"])

    def test_attempts_do_not_leak_state_into_one_another(self) -> None:
        """Each attempt starts from the committed state, not the previous outcome."""
        before = json.dumps(run.load(SESSION), sort_keys=True)
        self.assertEqual(run.evaluate(run.load(REFUSALS_CASE)), [])
        self.assertEqual(json.dumps(run.load(SESSION), sort_keys=True), before)


class GuardCompositionTests(unittest.TestCase):
    """Both guards apply, and each still stands on its own."""

    def session(self) -> dict:
        return run.load("evals/fixtures/approval/gates.session.json")

    def bound(self, session: dict, gate: str, target_id: str) -> dict:
        return approval.bind_approval(
            session, gate, target_id,
            {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"},
        )

    def test_the_sequence_guard_is_callable_alone(self) -> None:
        session = dict(self.session(), phase="intake")
        refusal = approval.sequence_refusal(
            session, {"gate": "decision_approval", "to_phase": "monitoring"}
        )
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal.code, approval.INVARIANT_VIOLATION)

    def test_the_sequence_guard_permits_a_legal_transition(self) -> None:
        session = dict(self.session(), phase="framing")
        self.assertIsNone(
            approval.sequence_refusal(session, {"gate": "frame_selection", "to_phase": "causal"})
        )

    def test_a_perfect_approval_in_the_wrong_phase_is_refused(self) -> None:
        session = dict(self.session(), phase="intake")
        transition = {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"}
        result = approval.attempt_transition(
            session, transition, self.bound(session, "decision_approval", "node_decision_001")
        )
        self.assertEqual(result["outcome"], "refused")
        self.assertIn("decision_approval", result["detail"])
        self.assertIn("intake", result["detail"])

    def test_the_same_approval_in_the_right_phase_is_accepted(self) -> None:
        """The sequence guard refuses a phase, not the approval."""
        session = dict(self.session(), phase="decision")
        transition = {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"}
        result = approval.attempt_transition(
            session, transition, self.bound(session, "decision_approval", "node_decision_001")
        )
        self.assertEqual(result["outcome"], "accepted", result["detail"])

    def test_a_legal_sequence_with_no_approval_is_still_refused(self) -> None:
        """Adding the sequence guard must not weaken the binding one."""
        session = dict(self.session(), phase="decision")
        transition = {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"}
        result = approval.attempt_transition(session, transition, None)
        self.assertEqual(result["code"], approval.APPROVAL_REQUIRED)

    def test_a_legal_sequence_with_an_unauthorized_actor_is_still_refused(self) -> None:
        session = dict(self.session(), phase="decision")
        bound = self.bound(session, "decision_approval", "node_decision_001")
        bound["actor"] = {"id": "user_someone", "kind": "human", "role": "observer"}
        transition = {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"}
        result = approval.attempt_transition(session, transition, bound)
        self.assertEqual(result["code"], approval.INVARIANT_VIOLATION)
        self.assertIn("lacks authority", result["detail"])

    def test_every_gate_is_accepted_from_its_own_phase_and_refused_elsewhere(self) -> None:
        from frameshift.orchestration import phases

        for name, gate in phases.GATES.items():
            with self.subTest(gate=name):
                elsewhere = next(p for p in phases.PHASES if p != gate.from_phase)
                session = dict(self.session(), phase=elsewhere)
                transition = {"gate": name, "to_phase": gate.to_phase}
                self.assertIsNotNone(approval.sequence_refusal(session, transition))
                allowed = dict(self.session(), phase=gate.from_phase)
                self.assertIsNone(approval.sequence_refusal(allowed, transition))

    def test_every_attempt_in_the_corpus_declares_where_it_stands(self) -> None:
        for path in sorted(run.FIXTURES.glob("approval-*.case.json")):
            case = run.load(str(path.relative_to(run.ROOT)))
            for attempt in case.get("attempts", []):
                with self.subTest(case=case["id"], attempt=attempt["id"]):
                    self.assertIn("from_phase", attempt)


if __name__ == "__main__":
    unittest.main()
