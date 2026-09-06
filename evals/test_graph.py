from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run
from evals.checks import graph


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


if __name__ == "__main__":
    unittest.main()
