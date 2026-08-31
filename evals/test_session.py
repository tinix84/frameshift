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

    def test_every_violation_carries_the_published_invariant_code(self) -> None:
        """A dangling reference is an invariant violation, which #24 already publishes."""
        state = reference_session()
        state["active_frame_id"] = "frame_never_created"
        state["graph"]["edges"][0]["target"] = "node_removed_001"
        violations = session.reference_violations(state)
        self.assertEqual(len(violations), 2, violations)
        self.assertTrue(
            all(item.startswith(session.INVARIANT_VIOLATION) for item in violations), violations
        )
        # The descriptive phrase stays in the message, where it helps a reader.
        self.assertTrue(all("dangling reference" in item for item in violations), violations)


class ProvenanceNamespaceTests(unittest.TestCase):
    """ADR-0012: the prefix names the namespace, the namespace decides resolution."""

    def test_the_registry_mirrors_the_table_in_context_md(self) -> None:
        """`CONTEXT.md` is the contract; this list is a mirror of it."""
        text = session.CONTEXT.read_text(encoding="utf-8")
        table = text.partition("| Prefix | Names | Lives in canonical state |")[2].partition("\n\n")[0]
        declared_local, declared_external = set(), set()
        for line in table.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 3 or not cells[0].startswith("`"):
                continue
            prefix = cells[0].strip("`")
            (declared_local if cells[2] == "yes" else declared_external).add(prefix)
        self.assertTrue(declared_local and declared_external, "the table must be readable")
        self.assertEqual(declared_local, set(session.SESSION_LOCAL_PREFIXES))
        self.assertEqual(declared_external, set(session.EXTERNAL_PREFIXES))

    def test_an_external_citation_is_accepted_on_its_prefix(self) -> None:
        state = reference_session()
        cited = {
            source
            for _, node in enumerate(state["graph"]["nodes"])
            for source in node.get("provenance", {}).get("source_ids", [])
        }
        external = {item for item in cited if item.startswith(session.EXTERNAL_PREFIXES)}
        self.assertTrue(external, "the reference session cites something outside state")
        self.assertEqual(session.reference_violations(state), [])

    def test_a_dangling_session_local_citation_is_caught(self) -> None:
        state = reference_session()
        state["graph"]["nodes"][0]["provenance"]["source_ids"] = ["stmt_999"]
        violations = session.reference_violations(state)
        self.assertTrue(any("stmt_999" in item for item in violations), violations)
        self.assertTrue(any("source_ids[0]" in item for item in violations), violations)

    def test_an_undeclared_namespace_is_caught_rather_than_assumed_external(self) -> None:
        """The openness must not become an escape hatch for dangling references."""
        state = reference_session()
        state["graph"]["nodes"][0]["provenance"]["source_ids"] = ["xyz_001"]
        violations = session.reference_violations(state)
        self.assertTrue(any("undeclared provenance namespace" in item for item in violations), violations)

    def test_every_session_local_prefix_resolves_or_fails(self) -> None:
        for prefix in session.SESSION_LOCAL_PREFIXES:
            with self.subTest(prefix=prefix):
                state = reference_session()
                state["graph"]["nodes"][0]["provenance"]["source_ids"] = [f"{prefix}absent"]
                self.assertTrue(session.reference_violations(state), prefix)

    def test_every_external_prefix_is_accepted(self) -> None:
        for prefix in session.EXTERNAL_PREFIXES:
            with self.subTest(prefix=prefix):
                state = reference_session()
                state["graph"]["nodes"][0]["provenance"]["source_ids"] = [f"{prefix}absent"]
                self.assertEqual(session.reference_violations(state), [], prefix)

    def test_citations_are_found_at_any_depth(self) -> None:
        state = reference_session()
        found = dict(session.walk_source_ids(state))
        self.assertIn("stmt_001", found)
        self.assertTrue(any(path.startswith("$.graph.nodes[") for path in found.values()))


class ScopeTests(unittest.TestCase):

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
