from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run
from evals.checks import graph, session
from frameshift.validation import invariants


class GraphInvariantTests(unittest.TestCase):
    def test_named_fixtures_prove_each_outcome(self) -> None:
        for name in (
            "graph-invariants",
            "graph-contradiction-preserves-both-claims",
            "graph-dangling-endpoint",
            "graph-deleted-endpoint",
            "graph-causes-requires-owner",
            "graph-causes-with-owner",
            "graph-causes-missing-confidence",
            "graph-causes-missing-provenance",
            "graph-self-loop-requires-flag",
            "graph-self-loop-explicit-feedback",
        ):
            with self.subTest(case=name):
                self.assertEqual(run.evaluate(run.load(f"evals/fixtures/{name}.case.json")), [])

    def test_runtime_and_reference_reject_graph_faults_identically(self) -> None:
        original = run.load("evals/fixtures/reference.checkpoint.json")["state"]
        for field, value, message in (
            ("type", "causes", "$.graph.edges[0].owner is required for a causes edge"),
            ("target", original["graph"]["edges"][0]["source"],
             "self-loop at $.graph.edges[0] requires feedback_loop: true"),
        ):
            with self.subTest(field=field):
                value_with_fault = copy.deepcopy(original)
                value_with_fault["graph"]["edges"][0][field] = value
                actual = invariants.reference_violations(value_with_fault)
                self.assertIn("invariant_violation: " + message, actual)
                self.assertEqual(actual, session.reference_violations(value_with_fault))

    def test_contradiction_keeps_original_claim_and_edge(self) -> None:
        value = run.load("evals/fixtures/graph-contradiction.json")
        original = copy.deepcopy(value)
        case = run.load("evals/fixtures/graph-contradiction-preserves-both-claims.case.json")
        self.assertEqual(graph.graph_invariants(case, lambda _: value), [])
        self.assertEqual({node["id"] for node in value["nodes"]}, {"node_claim", "node_counter"})
        self.assertEqual(value["edges"][0]["type"], "contradicts")
        self.assertEqual(value, original)

    def test_schema_violation_is_reported_before_graph_invariants(self) -> None:
        value = run.load("evals/fixtures/graph-base.json")
        value["edges"] = [None]
        case = {
            "artifact": "graph-base.json",
            "expect": {
                "outcome": "invalid",
                "violations_naming": ["$.edges[0]: must be object"],
            },
        }
        errors = graph.graph_invariants(case, lambda _: value)
        self.assertEqual(errors, [])

    def test_standalone_graph_rejects_unknown_and_dangling_node_provenance(self) -> None:
        value = run.load("evals/fixtures/graph-base.json")
        value["nodes"][0]["provenance"]["source_ids"] = ["node_missing"]
        violations = graph.graph_violations(value)
        self.assertTrue(any("node_missing" in item for item in violations), violations)
        value["nodes"][0]["provenance"]["source_ids"] = ["unknown_001"]
        self.assertTrue(any("undeclared provenance namespace" in item for item in graph.graph_violations(value)))


if __name__ == "__main__":
    unittest.main()
