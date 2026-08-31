#!/usr/bin/env python3
"""Tests for the persistence port.

The harness proves the encoder agrees with the reference on the committed
checkpoint. These prove the encoder's rules hold on inputs the reference
checkpoint does not happen to contain, and that restore reports what it did
rather than what it intended.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.persistence import canonical, checkpoint  # noqa: E402

REFERENCE = ROOT / "evals" / "fixtures" / "reference.checkpoint.json"


def reference_checkpoint() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


class CanonicalizationRuleTests(unittest.TestCase):
    """#22's seven rules, each on an input that isolates it."""

    def test_keys_are_sorted(self) -> None:
        self.assertEqual(canonical.encode(canonical.canonicalize({"b": 1, "a": 2})), '{"a":2,"b":1}')

    def test_set_like_arrays_are_ordered_and_others_are_not(self) -> None:
        self.assertIn("source_ids", canonical.set_like_fields())
        ordered = canonical.canonicalize({"source_ids": ["stmt_002", "stmt_001"]})
        self.assertEqual(ordered["source_ids"], ["stmt_001", "stmt_002"])
        kept = canonical.canonicalize({"levels": ["component", "business"]})
        self.assertEqual(kept["levels"], ["component", "business"])

    def test_nan_and_infinity_are_refused(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(canonical.CanonicalizationError):
                canonical.digest({"value": value})

    def test_line_endings_are_normalized(self) -> None:
        self.assertEqual(canonical.digest({"a": "x\r\ny"}), canonical.digest({"a": "x\ny"}))

    def test_one_instant_has_one_spelling(self) -> None:
        base = canonical.digest({"created_at": "2026-07-15T09:14:00Z"})
        for spelling in ("2026-07-15T09:14:00+00:00", "2026-07-15t09:14:00z", "2026-07-15T11:14:00+02:00"):
            with self.subTest(spelling=spelling):
                self.assertEqual(canonical.digest({"created_at": spelling}), base)

    def test_a_non_zero_fraction_survives(self) -> None:
        self.assertEqual(
            canonical.normalize_timestamp("2026-07-15T09:14:00.500Z"), "2026-07-15T09:14:00.5Z"
        )

    def test_the_digest_is_sha256_prefixed(self) -> None:
        self.assertTrue(canonical.digest({"a": 1}).startswith("sha256:"))

    def test_a_non_json_value_is_refused(self) -> None:
        with self.assertRaises(canonical.CanonicalizationError):
            canonical.digest({"when": object()})


class ExclusionTests(unittest.TestCase):
    def test_envelope_execution_metadata_leaves_the_checkpoint_digest_alone(self) -> None:
        reference = reference_checkpoint()
        baseline = canonical.checkpoint_digest(reference)
        for field in canonical.ENVELOPE_EXECUTION_METADATA:
            with self.subTest(field=field):
                mutated = copy.deepcopy(reference)
                mutated[field] = "anything"
                self.assertEqual(canonical.checkpoint_digest(mutated), baseline)

    def test_an_approval_timestamp_is_inside_the_state_digest(self) -> None:
        reference = reference_checkpoint()
        mutated = copy.deepcopy(reference)
        mutated["state"]["approvals"][0]["created_at"] = "2031-01-01T00:00:00Z"
        self.assertNotEqual(canonical.state_digest(mutated), canonical.state_digest(reference))


class EncodeTests(unittest.TestCase):
    def test_encoding_reproduces_the_committed_digests(self) -> None:
        reference = reference_checkpoint()
        bare = {k: v for k, v in reference.items() if k not in ("state_digest", "checkpoint_digest")}
        encoded = checkpoint.encode(bare)
        self.assertEqual(encoded["state_digest"], reference["state_digest"])
        self.assertEqual(encoded["checkpoint_digest"], reference["checkpoint_digest"])

    def test_encoding_is_idempotent(self) -> None:
        once = checkpoint.encode(reference_checkpoint())
        self.assertEqual(checkpoint.encode(once), once)


class RestoreTests(unittest.TestCase):
    def artifacts(self, reference: dict) -> dict[str, bytes]:
        return {
            item["id"]: (ROOT / item["uri"]).read_bytes().replace(b"\r\n", b"\n")
            for item in reference.get("artifacts", [])
        }

    def test_a_verified_checkpoint_yields_a_plan_and_no_actions(self) -> None:
        reference = reference_checkpoint()
        plan = checkpoint.restore(reference, self.artifacts(reference))
        self.assertEqual(plan["outcome"], "verified")
        self.assertEqual(plan["executed_capabilities"], [])
        self.assertEqual(plan["committed_proposal_ids"], [])
        self.assertTrue(plan["pending_proposal_ids"])

    def test_a_corrupt_checkpoint_yields_no_plan(self) -> None:
        reference = reference_checkpoint()
        reference["state"]["title"] = "tampered"
        plan = checkpoint.restore(reference, self.artifacts(reference))
        self.assertEqual(plan["outcome"], "refused")
        self.assertEqual(plan["pending_proposal_ids"], [])

    def test_the_journal_makes_an_action_visible(self) -> None:
        """The whole point of #102: 'it did nothing' is measured, not asserted."""
        reference = reference_checkpoint()
        journal = checkpoint.RestoreJournal()
        journal.record_execution("code.execute.sandboxed")
        journal.record_commit("prop_frame_001")
        plan = checkpoint.restore(reference, self.artifacts(reference), journal)
        self.assertEqual(plan["executed_capabilities"], ["code.execute.sandboxed"])
        self.assertEqual(plan["committed_proposal_ids"], ["prop_frame_001"])
        self.assertTrue(journal.acted)

    def test_a_correct_restore_never_writes_to_the_journal(self) -> None:
        reference = reference_checkpoint()
        journal = checkpoint.RestoreJournal()
        checkpoint.restore(reference, self.artifacts(reference), journal)
        self.assertFalse(journal.acted)

    def test_limits_are_applied_before_digests(self) -> None:
        reference = reference_checkpoint()
        deep: object = "bottom"
        for _ in range(200):
            deep = [deep]
        reference["state"]["title"] = deep
        violations = checkpoint.verify(reference, {})
        self.assertTrue(any(checkpoint.LIMIT_VIOLATION in item for item in violations))
        self.assertFalse(any(checkpoint.INTEGRITY_VIOLATION in item for item in violations))

    def test_a_missing_artifact_is_an_integrity_failure(self) -> None:
        reference = reference_checkpoint()
        violations = checkpoint.verify(reference, {})
        self.assertTrue(any("is missing" in item for item in violations), violations)


if __name__ == "__main__":
    unittest.main()
