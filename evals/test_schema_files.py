#!/usr/bin/env python3
"""Tests that schema well-formedness catches faults an artifact would not.

The point of this check is coverage an artifact-driven walk cannot reach, so
every case here plants its fault somewhere no fixture validates against — an
unreferenced `$defs` entry — and asserts it is still caught.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import schema, schema_files  # noqa: E402

CASE = "evals/fixtures/schemas-are-well-formed.case.json"


class PlantedSchema:
    """Add an unreferenced `$defs` entry to a real schema for one assertion."""

    def __init__(self, name: str, definition: dict) -> None:
        self.path = schema.SCHEMAS / name
        self.definition = definition

    def __enter__(self) -> None:
        self.original = self.path.read_bytes()
        document = json.loads(self.original.decode("utf-8"))
        document.setdefault("$defs", {})["_probe"] = self.definition
        self.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="")

    def __exit__(self, *exc: object) -> None:
        self.path.write_bytes(self.original)


class CleanRepositoryTests(unittest.TestCase):
    def test_every_committed_schema_is_well_formed(self) -> None:
        self.assertEqual(run.evaluate(run.load(CASE)), [])

    def test_all_six_schemas_are_walked(self) -> None:
        self.assertEqual(len(schema_files.schema_files()), 6)

    def test_the_schema_count_floor_is_enforced(self) -> None:
        case = run.load(CASE)
        case["expect"] = dict(case["expect"], min_schemas=99)
        errors = run.evaluate(case)
        self.assertTrue(any("case expects at least 99" in item for item in errors), errors)


class PlantedFaultTests(unittest.TestCase):
    """Each fault sits in a `$defs` entry nothing references."""

    def test_a_misspelled_keyword_is_caught_and_located(self) -> None:
        with PlantedSchema("common.schema.json", {"type": "object", "requred": ["id"]}):
            violations = schema_files.file_violations("common.schema.json")
        self.assertTrue(any("$.$defs._probe" in item for item in violations), violations)
        self.assertTrue(any("requred" in item for item in violations), violations)

    def test_an_unreferenced_fault_still_fails_the_case(self) -> None:
        """This is the coverage `artifact_conformance` cannot provide."""
        with PlantedSchema("graph.schema.json", {"type": "object", "requred": ["id"]}):
            errors = run.evaluate(run.load(CASE))
        self.assertTrue(errors, "an unreferenced malformed subschema must fail")

    def test_a_ref_to_a_missing_file_is_caught(self) -> None:
        with PlantedSchema("session.schema.json", {"$ref": "not-a-schema.json#/$defs/id"}):
            violations = schema_files.file_violations("session.schema.json")
        self.assertTrue(any("does not resolve" in item for item in violations), violations)

    def test_a_ref_to_a_missing_anchor_is_caught(self) -> None:
        with PlantedSchema("session.schema.json", {"$ref": "common.schema.json#/$defs/nonexistent"}):
            violations = schema_files.file_violations("session.schema.json")
        self.assertTrue(any("does not resolve" in item for item in violations), violations)

    def test_a_nested_fault_is_reported_with_its_path(self) -> None:
        definition = {"type": "object", "properties": {"inner": {"type": "array", "itms": {}}}}
        with PlantedSchema("common.schema.json", definition):
            violations = schema_files.file_violations("common.schema.json")
        self.assertTrue(
            any("$.$defs._probe.properties.inner" in item for item in violations), violations
        )

    def test_a_subschema_position_holding_a_non_object_is_caught(self) -> None:
        with PlantedSchema("common.schema.json", {"properties": {"inner": "not a schema"}}):
            violations = schema_files.file_violations("common.schema.json")
        self.assertTrue(any("expected a subschema object" in item for item in violations), violations)

    def test_the_schema_is_restored_after_each_plant(self) -> None:
        before = (schema.SCHEMAS / "common.schema.json").read_bytes()
        with PlantedSchema("common.schema.json", {"requred": []}):
            pass
        self.assertEqual((schema.SCHEMAS / "common.schema.json").read_bytes(), before)


class LeafKeywordTests(unittest.TestCase):
    """Values that look like subschemas but are not must be left alone."""

    def test_enum_values_are_not_walked_as_subschemas(self) -> None:
        with PlantedSchema("common.schema.json", {"enum": [{"requred": ["id"]}, "plain"]}):
            self.assertEqual(schema_files.file_violations("common.schema.json"), [])

    def test_const_values_are_not_walked_as_subschemas(self) -> None:
        with PlantedSchema("common.schema.json", {"const": {"requred": ["id"]}}):
            self.assertEqual(schema_files.file_violations("common.schema.json"), [])

    def test_a_boolean_additional_properties_is_accepted(self) -> None:
        with PlantedSchema("common.schema.json", {"type": "object", "additionalProperties": False}):
            self.assertEqual(schema_files.file_violations("common.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
