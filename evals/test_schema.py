#!/usr/bin/env python3
"""Tests that the validator enforces what it accepts.

A validator that accepts a keyword and then ignores it is worse than one that
refuses it, because the schema author believes the constraint is live. #117 was
exactly that: `additionalProperties` as a subschema passed `_check_keywords` and
then did nothing, so `contracts.engines` declared "name to version string" and
any shape satisfied it.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import schema  # noqa: E402

CHECKPOINT = "checkpoint.schema.json"


def keywords_in_committed_schemas() -> set[str]:
    """Every keyword appearing at a subschema position in `schemas/`."""
    from evals.checks import schema_files

    found: set[str] = set()

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        found.update(node)
        for keyword in ("items", "additionalProperties"):
            if isinstance(node.get(keyword), dict):
                visit(node[keyword])
        for item in node.get("anyOf", []):
            visit(item)
        for keyword in ("properties", "$defs"):
            for value in node.get(keyword, {}).values():
                visit(value)

    for name in schema_files.schema_files():
        visit(schema.load_schema(name))
    return found


class KeywordPartitionTests(unittest.TestCase):
    def test_enforced_and_annotations_partition_supported(self) -> None:
        self.assertEqual(schema.ENFORCED | schema.ANNOTATIONS, schema.SUPPORTED)
        self.assertEqual(schema.ENFORCED & schema.ANNOTATIONS, frozenset())

    def test_no_committed_schema_uses_a_keyword_the_validator_ignores(self) -> None:
        """The general form of #117: accepted-and-ignored must be impossible."""
        used = keywords_in_committed_schemas()
        self.assertTrue(used, "the walk must actually reach the schemas")
        self.assertEqual(used - schema.SUPPORTED, set(), "unsupported keyword in a committed schema")
        ignored = used & (schema.SUPPORTED - schema.ENFORCED - schema.ANNOTATIONS)
        self.assertEqual(ignored, set(), f"keywords accepted but never applied: {sorted(ignored)}")

    def test_additional_properties_is_classified_as_enforced(self) -> None:
        self.assertIn("additionalProperties", schema.ENFORCED)


class AdditionalPropertiesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = schema.load_schema(CHECKPOINT)
        self.checkpoint = run.load("evals/fixtures/reference.checkpoint.json")

    def validate(self, artifact: object) -> list[str]:
        return schema.validate(artifact, self.schema, current=CHECKPOINT)

    def test_the_reference_checkpoint_still_validates(self) -> None:
        self.assertEqual(self.validate(self.checkpoint), [])

    def test_a_non_string_engine_contract_is_caught_and_named(self) -> None:
        broken = copy.deepcopy(self.checkpoint)
        broken["contracts"]["engines"]["problem_framing"] = {"totally": "wrong", "shape": 42}
        errors = self.validate(broken)
        self.assertTrue(
            any("$.contracts.engines.problem_framing" in item for item in errors), errors
        )

    def test_a_non_string_prompt_contract_is_caught(self) -> None:
        broken = copy.deepcopy(self.checkpoint)
        broken["contracts"]["prompts"]["problem_framing"] = 42
        errors = self.validate(broken)
        self.assertTrue(
            any("$.contracts.prompts.problem_framing" in item for item in errors), errors
        )

    def test_a_further_valid_engine_contract_is_accepted(self) -> None:
        """The fix constrains the shape; it does not close the map."""
        widened = copy.deepcopy(self.checkpoint)
        widened["contracts"]["engines"]["causal_reasoning"] = "1.0.0"
        self.assertEqual(self.validate(widened), [])

    def test_additional_properties_false_still_closes_an_object(self) -> None:
        closed = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        errors = schema.validate({"a": "x", "b": "y"}, closed, current=CHECKPOINT)
        self.assertTrue(any("unexpected property 'b'" in item for item in errors), errors)

    def test_a_named_property_is_not_double_checked_by_the_subschema(self) -> None:
        mixed = {
            "type": "object",
            "properties": {"named": {"type": "integer"}},
            "additionalProperties": {"type": "string"},
        }
        self.assertEqual(schema.validate({"named": 1, "other": "x"}, mixed, current=CHECKPOINT), [])
        errors = schema.validate({"named": 1, "other": 2}, mixed, current=CHECKPOINT)
        self.assertTrue(any("$.other" in item for item in errors), errors)


class RegressionTests(unittest.TestCase):
    def test_the_committed_corpus_is_unaffected(self) -> None:
        case = run.load("evals/fixtures/committed-artifacts-match-their-schema.case.json")
        self.assertEqual(run.evaluate(case), [])

    def test_the_reproduction_from_the_issue_now_fails(self) -> None:
        artifact = json.loads(
            json.dumps(run.load("evals/fixtures/reference.checkpoint.json"))
        )
        artifact["contracts"]["engines"]["problem_framing"] = {"totally": "wrong", "shape": 42}
        self.assertNotEqual(
            schema.validate(artifact, schema.load_schema(CHECKPOINT), current=CHECKPOINT), []
        )


if __name__ == "__main__":
    unittest.main()
