#!/usr/bin/env python3
"""Tests for the orchestrator's guarded transitions.

The harness proves this reaches the same outcome as the reference guard on every
attempt the corpus declares. These prove the two guards stand apart, that the
authority table is the one CONTEXT.md names, and that each refusal carries a
code from the published vocabulary rather than an invented one.
"""

from __future__ import annotations

import copy
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


class CommittedEventTests(unittest.TestCase):
    """A committed transition emits events that fold to the state it produced."""

    def accepted(self, phase: str, gate: str, target_id: str, to_phase: str, role: str = "decision_owner"):
        state = session(phase)
        actor = {"id": "user_lead_eng", "kind": "human", "role": role}
        transition = {"gate": gate, "target_id": target_id, "to_phase": to_phase}
        result = transitions.attempt(state, transition, bound(state, target_id, actor))
        self.assertEqual(result["outcome"], "accepted", result["detail"])
        return state, result

    def test_an_advancing_gate_emits_an_approval_and_a_phase_change(self) -> None:
        _, result = self.accepted("decision", "decision_approval", "node_decision_001", "monitoring")
        self.assertEqual([e["type"] for e in result["events"]], ["approval.recorded", "phase.changed"])

    def test_a_same_phase_gate_emits_no_phase_change(self) -> None:
        """external_action guards an act, so it must not look like a boundary."""
        _, result = self.accepted("causal", "external_action", "node_decision_001", "causal", "operator")
        self.assertEqual([e["type"] for e in result["events"]], ["approval.recorded"])

    def test_a_refused_transition_records_nothing(self) -> None:
        state = session("intake")
        result = transitions.attempt(
            state,
            {"gate": "decision_approval", "target_id": "node_decision_001", "to_phase": "monitoring"},
            bound(state, "node_decision_001"),
        )
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["events"], [])

    def test_the_events_fold_to_the_state_the_transition_produced(self) -> None:
        from frameshift.persistence import canonical
        from evals.checks import replay

        state, result = self.accepted("decision", "decision_approval", "node_decision_001", "monitoring")
        expected = copy.deepcopy(state)
        expected["approvals"] = expected.get("approvals", []) + [result["events"][0]["payload"]]
        expected["phase"] = "monitoring"

        folded = copy.deepcopy(state)
        for index, body in enumerate(result["events"], start=1):
            replay._apply(folded, dict(body, sequence=index, event_id=f"evt_{index:03d}"))

        self.assertEqual(canonical.digest(folded), canonical.digest(expected))

    def test_every_emitted_event_type_has_a_reducer(self) -> None:
        """An event the log cannot replay is a gap in history, not a detail."""
        from evals.checks import replay

        for gate in phases.GATES.values():
            with self.subTest(gate=gate.name):
                state = session(gate.from_phase)
                role = sorted(transitions.GATE_AUTHORITY[gate.name])[0]
                actor = {"id": "user_lead_eng", "kind": "human", "role": role}
                transition = {
                    "gate": gate.name,
                    "target_id": "node_decision_001",
                    "to_phase": gate.to_phase,
                }
                result = transitions.attempt(state, transition, bound(state, "node_decision_001", actor))
                self.assertEqual(result["outcome"], "accepted", result["detail"])
                for body in result["events"]:
                    folded = copy.deepcopy(state)
                    replay._apply(folded, dict(body, sequence=1, event_id="evt_001"))


if __name__ == "__main__":
    unittest.main()
