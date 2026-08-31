#!/usr/bin/env python3
"""Tests that artifact conformance would fail if a schema stopped constraining.

A conformance check whose mapping matches nothing passes loudly and proves
nothing. These assert the mapping reaches real files, that a planted violation
is caught and named, and that an exclusion cannot quietly hide an artifact.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import artifacts  # noqa: E402

CASE = "evals/fixtures/committed-artifacts-match-their-schema.case.json"


class MappingTests(unittest.TestCase):
    def test_the_declared_case_passes(self) -> None:
        self.assertEqual(run.evaluate(run.load(CASE)), [])

    def test_every_capability_manifest_is_governed(self) -> None:
        case = run.load(CASE)
        governed = dict(artifacts.governed_artifacts(case["governs"], case["deliberately_invalid"]))
        shipped = sorted(
            path.relative_to(artifacts.ROOT).as_posix()
            for path in artifacts.ROOT.glob("adapters/*/capabilities.json")
        )
        self.assertTrue(shipped, "the repository ships capability manifests")
        for relative in shipped:
            self.assertEqual(governed.get(relative), "capability-manifest.schema.json", relative)

    def test_a_mapping_that_matches_nothing_fails(self) -> None:
        case = run.load(CASE)
        case["governs"] = dict(case["governs"], **{"adapters/*/nothing-here.json": "capability-manifest.schema.json"})
        errors = run.evaluate(case)
        self.assertTrue(any("checks nothing" in item for item in errors), errors)

    def test_an_empty_mapping_fails(self) -> None:
        case = run.load(CASE)
        case["governs"] = {}
        self.assertTrue(run.evaluate(case))

    def test_the_artifact_count_floor_is_enforced(self) -> None:
        case = run.load(CASE)
        case["expect"] = dict(case["expect"], min_artifacts=999)
        errors = run.evaluate(case)
        self.assertTrue(any("case expects at least 999" in item for item in errors), errors)


class ViolationTests(unittest.TestCase):
    def test_a_manifest_violating_its_schema_is_caught_and_named(self) -> None:
        manifest = artifacts.ROOT / "adapters" / "generic" / "capabilities.json"
        original = manifest.read_bytes()
        try:
            manifest.write_text('{"schema_version": "0.0.1"}\n', encoding="utf-8", newline="")
            errors = run.evaluate(run.load(CASE))
        finally:
            manifest.write_bytes(original)
        self.assertTrue(errors, "a broken manifest must fail conformance")
        self.assertTrue(
            any("adapters/generic/capabilities.json" in item for item in errors), errors
        )

    def test_the_unrepairable_fixture_really_is_invalid(self) -> None:
        """The exclusion is earned: this artifact does not satisfy its schema."""
        from evals.checks import schema

        case = run.load(CASE)
        relative = "evals/fixtures/repair/unnamed-engine.repaired.json"
        self.assertIn(relative, case["deliberately_invalid"])
        found = schema.validate(
            run.load(relative),
            schema.load_schema("engine-result.schema.json"),
            current="engine-result.schema.json",
        )
        self.assertTrue(found, "an excused artifact that is actually valid should not be excused")

    def test_excusing_an_artifact_that_does_not_exist_fails(self) -> None:
        case = run.load(CASE)
        case["deliberately_invalid"] = dict(
            case["deliberately_invalid"], **{"evals/fixtures/not-a-file.json": "typo"}
        )
        errors = run.evaluate(case)
        self.assertTrue(any("does not exist" in item for item in errors), errors)

    def test_an_excused_artifact_is_not_validated(self) -> None:
        case = run.load(CASE)
        without = copy.deepcopy(case)
        without["deliberately_invalid"] = {}
        self.assertTrue(run.evaluate(without), "without the exclusion the corpus fixture fails")


if __name__ == "__main__":
    unittest.main()
