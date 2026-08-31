#!/usr/bin/env python3
"""Tests for the orchestrator's guarded transitions.

The harness proves this reaches the same outcome as the reference guard on every
attempt the corpus declares. These prove the two guards stand apart, that the
authority table is the one CONTEXT.md names, and that each refusal carries a
code from the published vocabulary rather than an invented one.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration import phases, transitions  # noqa: E402

SESSION = ROOT / "evals" / "fixtures" / "approval" / "gates.session.json"
OWNER = {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"}
PUBLISHED = {
    "approval_required",
    "approval_stale",
    "invariant_violation",
}


def session(phase: str) -> dict:
    state = json.loads(SESSION.read_text(encoding="utf-8"))
    state["phase"] = phase
    return state


def bound(state: dict, target_id: str, actor: dict = OWNER) -> dict:
    target = transitions.find_target(state, target_id)
    return {
        "id": "appr_test",
        "target_id": target_id,
        "target_digest": transitions.content_digest(target),
        "disposition": "approved",
        "actor": actor,
        "session_revision": state["revision"],
        "created_at": "2026-07-16T10:00:00Z",
    }


class AuthorityTests(unittest.TestCase):
    def test_the_table_covers_exactly_the_eight_gates(self) -> None:
        self.assertEqual(set(transitions.GATE_AUTHORITY), set(phases.GATES))

    def test_every_gate_names_at_least_one_role(self) -> None:
        for gate, roles in transitions.GATE_AUTHORITY.items():
            with self.subTest(gate=gate):
                self.assertTrue(roles)

    def test_knowledge_promotion_belongs_to_the_workspace_owner(self) -> None:
        self.assertEqual(transitions.GATE_AUTHORITY["knowledge_promotion"], frozenset({"workspace_owner"}))


class SeparateGuardTests(unittest.TestCase):
    """Sequence and binding answer different questions and are callable apart."""

    def test_the_sequence_guard_alone_refuses_the_wrong_phase(self) -> None:
        refusal = transitions.sequence_refusal(
            session("intake"), {"gate": "decision_approval", "to_phase": "monitoring"}
        )
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal.code, transitions.INVARIANT_VIOLATION)

    def test_the_sequence_guard_alone_permits_the_right_phase(self) -> None:
        self.assertIsNone(
            transitions.sequence_refusal(
                session("framing"), {"gate": "frame_selection", "to_phase": "causal"}
            )
        )

    def test_the_binding_guard_alone_refuses_a_missing_approval(self) -> None:
        state = session("decision")
        refusal = transitions.binding_refusal(
            state, {"gate": "decision_approval", "target_id": "node_decision_001"}, None
        )
        self.assertEqual(refusal.code, transitions.APPROVAL_REQUIRED)

    def test_the_binding_guard_alone_accepts_a_bound_approval(self) -> None:
        state = session("decision")
        transition = {"gate": "decision_approval", "target_id": "node_decision_001"}
        self.assertIsNone(
            transitions.binding_refusal(state, transition, bound(state, "node_decision_001"))
        )


class AttemptTests(unittest.TestCase):
    def test_a_legal_bound_transition_is_accepted(self) -> None:
        state = session("decision")
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            bound(state, "node_decision_001"),
        )
        self.assertEqual(result["outcome"], "accepted", result["detail"])
        self.assertEqual(result["phase"], "monitoring")

    def test_sequence_is_refused_before_binding_is_weighed(self) -> None:
        """A perfect approval in the wrong phase reports the phase, not the approval."""
        state = session("intake")
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            bound(state, "node_decision_001"),
        )
        self.assertEqual(result["outcome"], "refused")
        self.assertIn("decision_approval", result["detail"])

    def test_a_stale_revision_is_refused(self) -> None:
        state = session("decision")
        approval = dict(bound(state, "node_decision_001"), session_revision=1)
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            approval,
        )
        self.assertEqual(result["code"], transitions.APPROVAL_STALE)

    def test_an_unauthorized_role_is_refused(self) -> None:
        state = session("decision")
        approval = bound(state, "node_decision_001", {"id": "u", "kind": "human", "role": "observer"})
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            approval,
        )
        self.assertEqual(result["code"], transitions.INVARIANT_VIOLATION)
        self.assertIn("lacks authority", result["detail"])

    def test_a_runtime_cannot_approve_on_a_humans_behalf(self) -> None:
        state = session("decision")
        approval = bound(state, "node_decision_001", {"id": "bot", "kind": "runtime", "role": "decision_owner"})
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            approval,
        )
        self.assertIn("cannot approve", result["detail"])

    def test_an_unknown_gate_is_refused(self) -> None:
        result = transitions.attempt(session("decision"), {"gate": "teleport", "target_id": "x"}, None)
        self.assertEqual(result["outcome"], "refused")

    def test_a_missing_target_is_refused(self) -> None:
        state = session("decision")
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_absent", "to_phase": "monitoring"},
            None,
        )
        self.assertIn("no such target", result["detail"])

    def test_every_refusal_code_is_from_the_published_vocabulary(self) -> None:
        state = session("decision")
        cases = [
            ({"gate": "teleport", "target_id": "node_decision_001"}, None),
            ({"gate": "decision_approval", "target_id": "node_absent"}, None),
            ({"gate": "decision_approval", "target_id": "node_decision_001"}, None),
            (
                {"gate": "decision_approval", "target_id": "node_decision_001"},
                dict(bound(state, "node_decision_001"), session_revision=1),
            ),
        ]
        for transition, approval in cases:
            with self.subTest(transition=transition):
                result = transitions.attempt(state, transition, approval)
                self.assertEqual(result["outcome"], "refused")
                self.assertIn(result["code"], PUBLISHED)


if __name__ == "__main__":
    unittest.main()
