#!/usr/bin/env python3
"""Tests that the session invariants would fail if coherence broke.

The fixtures prove the reference session is coherent. These prove the check
notices when it is not, and that its deliberate limits are limits rather than
oversights.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import schema, session  # noqa: E402

REFERENCE = "evals/fixtures/reference.checkpoint.json"


def reference_session() -> dict:
    return run.load(REFERENCE)["state"]


class ReferenceIntegrityTests(unittest.TestCase):
    def test_the_reference_session_validates_against_its_schema(self) -> None:
        errors = schema.validate(
            reference_session(),
            schema.load_schema("session.schema.json"),
            current="session.schema.json",
        )
        self.assertEqual(errors, [])

    def test_the_reference_session_resolves_every_internal_reference(self) -> None:
        self.assertEqual(session.reference_violations(reference_session()), [])

    def test_the_standalone_gates_session_is_also_coherent(self) -> None:
        gates = run.load("evals/fixtures/approval/gates.session.json")
        self.assertEqual(session.reference_violations(gates), [])


class DanglingReferenceTests(unittest.TestCase):
    def test_an_edge_pointing_at_a_removed_node_is_caught(self) -> None:
        state = reference_session()
        state["graph"]["edges"][0]["target"] = "node_removed_001"
        violations = session.reference_violations(state)
        self.assertTrue(any("$.graph.edges[0].target" in item for item in violations), violations)

    def test_an_edge_source_is_checked_as_well_as_its_target(self) -> None:
        state = reference_session()
        state["graph"]["edges"][0]["source"] = "node_removed_001"
        violations = session.reference_violations(state)
        self.assertTrue(any("$.graph.edges[0].source" in item for item in violations), violations)

    def test_an_active_frame_that_never_existed_is_caught(self) -> None:
        state = reference_session()
        state["active_frame_id"] = "frame_never_created"
        violations = session.reference_violations(state)
        self.assertTrue(any("$.active_frame_id" in item for item in violations), violations)

    def test_an_absent_active_frame_is_not_a_violation(self) -> None:
        state = reference_session()
        del state["active_frame_id"]
        self.assertEqual(session.reference_violations(state), [])

    def test_an_approval_bound_to_a_deleted_target_is_caught(self) -> None:
        state = reference_session()
        state["approvals"][0]["target_id"] = "frame_deleted_001"
        violations = session.reference_violations(state)
        self.assertTrue(any("$.approvals[0].target_id" in item for item in violations), violations)

    def test_every_violation_carries_the_dangling_reference_code(self) -> None:
        state = reference_session()
        state["active_frame_id"] = "frame_never_created"
        state["graph"]["edges"][0]["target"] = "node_removed_001"
        violations = session.reference_violations(state)
        self.assertEqual(len(violations), 2, violations)
        self.assertTrue(all(item.startswith(session.DANGLING) for item in violations), violations)


class ScopeTests(unittest.TestCase):
    def test_provenance_source_ids_are_deliberately_not_resolved(self) -> None:
        """The reference cites an intake record and an artifact, neither in state."""
        state = reference_session()
        cited = {
            source
            for node in state["graph"]["nodes"]
            for source in node.get("provenance", {}).get("source_ids", [])
        }
        self.assertTrue(cited - session.node_ids(state) - session.collect_ids(state, "statements"))
        self.assertEqual(session.reference_violations(state), [])

    def test_a_schema_violation_is_reported_by_the_check(self) -> None:
        case = run.load("evals/fixtures/session-reference-integrity.case.json")
        case["mutate"] = [{"path": ["title"], "value": 42}]
        case["expect"] = {"outcome": "invalid", "violations_naming": ["$.title"]}
        self.assertEqual(run.evaluate(case), [])


class CaseWiringTests(unittest.TestCase):
    def test_the_declared_cases_pass(self) -> None:
        for name in (
            "session-reference-integrity",
            "session-dangling-edge-target",
            "session-active-frame-does-not-exist",
            "session-approval-target-is-unaddressable",
        ):
            with self.subTest(case=name):
                self.assertEqual(run.evaluate(run.load(f"evals/fixtures/{name}.case.json")), [])

    def test_a_negative_case_without_its_mutation_no_longer_fails(self) -> None:
        """Each negative case earns its keep: the planted incoherence is what fails it."""
        case = run.load("evals/fixtures/session-dangling-edge-target.case.json")
        del case["mutate"]
        self.assertTrue(run.evaluate(case))

    def test_at_reaches_the_session_inside_the_checkpoint(self) -> None:
        case = run.load("evals/fixtures/session-reference-integrity.case.json")
        self.assertEqual(case["at"], ["state"])
        without = copy.deepcopy(case)
        del without["at"]
        # Without `at` the check sees the envelope, which is not a session.
        self.assertTrue(run.evaluate(without))


if __name__ == "__main__":
    unittest.main()
