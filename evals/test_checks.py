#!/usr/bin/env python3
"""Tests that the checkpoint checks would fail if the property broke.

The fixtures prove the reference checkpoint is intact. These prove the checks
notice when it is not, and that the canonicalization rules are the ones the
schemas actually declare.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import canonical, checkpoint  # noqa: E402

REFERENCE = "evals/fixtures/reference.checkpoint.json"


def load_reference() -> dict:
    return run.load(REFERENCE)


class CanonicalizationTests(unittest.TestCase):
    def test_set_like_fields_match_the_schemas(self) -> None:
        """The list is a mirror of `uniqueItems: true`, not an independent opinion."""
        found: set[str] = set()

        def walk(node: object, key: str | None = None) -> None:
            if isinstance(node, dict):
                if node.get("type") == "array" and node.get("uniqueItems") and key:
                    found.add(key)
                for name, value in node.items():
                    walk(value, name)
            elif isinstance(node, list):
                for value in node:
                    walk(value, key)

        for path in sorted((run.ROOT / "schemas").glob("*.json")):
            walk(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(found, set(canonical.SET_LIKE_FIELDS))

    def test_nan_and_infinity_are_not_canonical(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(canonical.CanonicalizationError):
                canonical.digest({"value": value})

    def test_execution_metadata_never_reaches_the_digest(self) -> None:
        bare = canonical.digest({"a": 1})
        for field in canonical.EXECUTION_METADATA_FIELDS:
            self.assertEqual(canonical.digest({"a": 1, field: "anything"}), bare, field)

    def test_a_semantic_change_does_change_the_digest(self) -> None:
        self.assertNotEqual(canonical.digest({"a": 1}), canonical.digest({"a": 2}))


class DigestCheckTests(unittest.TestCase):
    def test_reference_checkpoint_passes(self) -> None:
        case = run.load("evals/fixtures/checkpoint-digest-stability.case.json")
        self.assertEqual(run.evaluate(case), [])

    def test_a_wrong_recorded_digest_fails(self) -> None:
        case = run.load("evals/fixtures/checkpoint-digest-stability.case.json")
        case["expect"]["state_digest"] = "sha256:" + "0" * 64
        errors = run.evaluate(case)
        self.assertTrue(any("state_digest drifted" in error for error in errors), errors)

    def test_an_unknown_perturbation_fails(self) -> None:
        case = run.load("evals/fixtures/checkpoint-digest-stability.case.json")
        case["expect"]["invariant_under"] = ["gravity"]
        errors = run.evaluate(case)
        self.assertTrue(any("unknown perturbation: gravity" in error for error in errors), errors)


class IntegrityTests(unittest.TestCase):
    def test_intact_checkpoint_verifies(self) -> None:
        reference = load_reference()
        payloads = {item["id"]: checkpoint.read_artifact(item["uri"]) for item in reference["artifacts"]}
        self.assertEqual(checkpoint.verify(reference, payloads), [])

    def test_every_mutated_byte_of_state_is_caught(self) -> None:
        reference = load_reference()
        payloads = {item["id"]: checkpoint.read_artifact(item["uri"]) for item in reference["artifacts"]}
        for path in (["state", "title"], ["state", "revision"], ["state", "phase"]):
            mutated = copy.deepcopy(reference)
            target = mutated["state"]
            target[path[-1]] = 99 if isinstance(target[path[-1]], int) else "tampered"
            violations = checkpoint.verify(mutated, payloads)
            self.assertTrue(any("state_digest" in item for item in violations), path)

    def test_restore_of_a_corrupt_checkpoint_produces_no_plan(self) -> None:
        reference = load_reference()
        reference["state"]["title"] = "tampered"
        payloads = {item["id"]: checkpoint.read_artifact(item["uri"]) for item in reference["artifacts"]}
        plan = checkpoint.plan_restore(reference, payloads)
        self.assertEqual(plan["outcome"], "refused")
        self.assertEqual(plan["pending_proposal_ids"], [])
        self.assertEqual(plan["executed_capabilities"], [])
        self.assertEqual(plan["committed_proposal_ids"], [])

    def test_restore_leaves_pending_proposals_pending(self) -> None:
        reference = load_reference()
        payloads = {item["id"]: checkpoint.read_artifact(item["uri"]) for item in reference["artifacts"]}
        plan = checkpoint.plan_restore(reference, payloads)
        self.assertEqual(plan["outcome"], "verified")
        self.assertTrue(plan["pending_proposal_ids"])
        self.assertEqual(plan["committed_proposal_ids"], [])
        self.assertEqual(plan["executed_capabilities"], [])
        self.assertIn("frame_selection", plan["required_checkpoints"])

    def test_a_missing_artifact_is_an_integrity_failure(self) -> None:
        reference = load_reference()
        violations = checkpoint.verify(reference, {})
        self.assertTrue(any("is missing" in item for item in violations), violations)


if __name__ == "__main__":
    unittest.main()
