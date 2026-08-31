#!/usr/bin/env python3
"""Tests for the validation port.

The harness proves this validator agrees with the reference fault for fault.
These prove the properties that agreement alone would not catch: that no
keyword is accepted and then ignored, that the provenance registry is read from
`CONTEXT.md` rather than restated, and that each invariant fires on its own.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.validation import invariants, schema  # noqa: E402

REFERENCE = ROOT / "evals" / "fixtures" / "reference.checkpoint.json"


def reference_session() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))["state"]


class KeywordDisciplineTests(unittest.TestCase):
    """#117: a keyword accepted and then ignored is worse than one refused."""

    def test_enforced_and_annotations_partition_supported(self) -> None:
        self.assertEqual(schema.ENFORCED | schema.ANNOTATIONS, schema.SUPPORTED)
        self.assertEqual(schema.ENFORCED & schema.ANNOTATIONS, frozenset())

    def test_every_enforced_keyword_is_applied_somewhere(self) -> None:
        structural = {"$ref", "$defs", "anyOf", "properties", "additionalProperties"}
        applied = set(schema._KEYWORDS) | structural
        self.assertEqual(schema.ENFORCED - applied, set(), "declared enforced but never applied")

    def test_no_handler_exists_for_a_keyword_that_is_not_enforced(self) -> None:
        self.assertEqual(set(schema._KEYWORDS) - schema.ENFORCED, set())

    def test_an_unsupported_keyword_raises_rather_than_passing(self) -> None:
        with self.assertRaises(schema.UnsupportedSchema):
            schema.validate("x", {"type": "string", "allOf": []}, current="common.schema.json")

    def test_every_committed_schema_uses_only_supported_keywords(self) -> None:
        """Walk each schema in full, including `$defs` no artifact reaches."""

        def keywords(node: object, found: set[str]) -> set[str]:
            if isinstance(node, dict):
                found.update(node)
                for keyword in ("items", "additionalProperties"):
                    if isinstance(node.get(keyword), dict):
                        keywords(node[keyword], found)
                for item in node.get("anyOf", []):
                    keywords(item, found)
                for keyword in ("properties", "$defs"):
                    for value in node.get(keyword, {}).values():
                        keywords(value, found)
            return found

        paths = sorted((ROOT / "schemas").glob("*.json"))
        self.assertTrue(paths, "there must be schemas to walk")
        for path in paths:
            with self.subTest(schema=path.name):
                used = keywords(json.loads(path.read_text(encoding="utf-8")), set())
                self.assertEqual(used - schema.SUPPORTED, set())


class AdditionalPropertiesTests(unittest.TestCase):
    def test_a_subschema_is_applied_to_unnamed_properties(self) -> None:
        rule = {
            "type": "object",
            "properties": {"named": {"type": "integer"}},
            "additionalProperties": {"type": "string"},
        }
        self.assertEqual(schema.validate({"named": 1, "other": "x"}, rule, current="common.schema.json"), [])
        errors = schema.validate({"named": 1, "other": 2}, rule, current="common.schema.json")
        self.assertTrue(any("$.other" in item for item in errors), errors)

    def test_false_still_closes_an_object(self) -> None:
        rule = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        errors = schema.validate({"a": "x", "b": "y"}, rule, current="common.schema.json")
        self.assertTrue(any("unexpected property 'b'" in item for item in errors), errors)

    def test_the_committed_contracts_block_is_constrained(self) -> None:
        checkpoint = json.loads(REFERENCE.read_text(encoding="utf-8"))
        self.assertEqual(schema.validate_against(checkpoint, "checkpoint.schema.json"), [])
        checkpoint["contracts"]["engines"]["problem_framing"] = {"wrong": "shape"}
        errors = schema.validate_against(checkpoint, "checkpoint.schema.json")
        self.assertTrue(any("$.contracts.engines.problem_framing" in item for item in errors), errors)


class ProvenanceRegistryTests(unittest.TestCase):
    def test_the_registry_is_read_from_the_glossary(self) -> None:
        local, external = invariants.provenance_namespaces()
        self.assertEqual(local, frozenset({"stmt_", "frame_", "node_", "opt_", "crit_"}))
        self.assertEqual(external, frozenset({"intake_", "art_"}))

    def test_the_registry_is_not_empty_if_the_table_moves(self) -> None:
        """A parser that silently matched nothing would make every citation legal."""
        local, external = invariants.provenance_namespaces()
        self.assertTrue(local and external)


class InvariantTests(unittest.TestCase):
    def test_the_reference_session_is_coherent(self) -> None:
        self.assertEqual(invariants.session_violations(reference_session()), [])

    def test_a_dangling_edge_is_caught(self) -> None:
        state = reference_session()
        state["graph"]["edges"][0]["target"] = "node_removed_001"
        self.assertTrue(any("$.graph.edges[0].target" in i for i in invariants.reference_violations(state)))

    def test_an_absent_active_frame_is_caught(self) -> None:
        state = reference_session()
        state["active_frame_id"] = "frame_never_created"
        self.assertTrue(any("$.active_frame_id" in i for i in invariants.reference_violations(state)))

    def test_an_unaddressable_approval_target_is_caught(self) -> None:
        state = reference_session()
        state["approvals"][0]["target_id"] = "frame_deleted_001"
        self.assertTrue(any("$.approvals[0].target_id" in i for i in invariants.reference_violations(state)))

    def test_an_external_citation_is_accepted(self) -> None:
        state = reference_session()
        state["graph"]["nodes"][0]["provenance"]["source_ids"] = ["intake_001", "art_evidence_001"]
        self.assertEqual(invariants.reference_violations(state), [])

    def test_a_dangling_session_local_citation_is_caught(self) -> None:
        state = reference_session()
        state["graph"]["nodes"][0]["provenance"]["source_ids"] = ["stmt_999"]
        self.assertTrue(any("stmt_999" in i for i in invariants.reference_violations(state)))

    def test_an_undeclared_namespace_is_caught(self) -> None:
        state = reference_session()
        state["graph"]["nodes"][0]["provenance"]["source_ids"] = ["xyz_001"]
        self.assertTrue(
            any("undeclared provenance namespace" in i for i in invariants.reference_violations(state))
        )

    def test_schema_violations_come_before_invariant_violations(self) -> None:
        state = reference_session()
        state["title"] = 42
        state["active_frame_id"] = "frame_never_created"
        found = invariants.session_violations(state)
        self.assertIn("$.title", found[0])
        self.assertTrue(any(invariants.INVARIANT_VIOLATION in item for item in found))


if __name__ == "__main__":
    unittest.main()
