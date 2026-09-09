"""The frame-axis contract and explicit checkpoint conversion (#86)."""

import copy
import json
import unittest
from pathlib import Path

from frameshift.persistence import checkpoint, migration
from frameshift.validation import schema

FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


def reference():
    return json.loads((FIXTURES / "reference.checkpoint.json").read_text(encoding="utf-8"))


def artifact_bytes():
    return {
        "art_evidence_001": (FIXTURES / "reference-evidence.txt").read_bytes(),
    }


TARGET_PROMPTS = {
    "problem_framing": {
        "id": "frameshift.problem-framing.v2",
        "version": "2.0.0",
        "digest": "sha256:bb57c98a14c2fd82ae287787c19cc079266a28160650326df33daf2cd685bea2",
    }
}


class FrameContractTests(unittest.TestCase):
    def test_two_independent_axes_validate_at_the_current_contract(self):
        state = reference()["state"]
        state["schema_version"] = "2.0.0"
        state["frames"][0]["system_boundary"] = "supply_chain"
        self.assertEqual(schema.validate_against(state, "session.schema.json"), [])
        self.assertEqual(state["frames"][0]["abstraction_level"], "product")

    def test_boundary_is_required_and_lateral_values_are_not_ladder_levels(self):
        state = reference()["state"]
        state["schema_version"] = "2.0.0"
        self.assertTrue(any("system_boundary" in e for e in schema.validate_against(state, "session.schema.json")))
        state["frames"][0]["system_boundary"] = "supply_chain"
        state["frames"][0]["abstraction_level"] = "supply_chain"
        self.assertTrue(any("abstraction_level" in e for e in schema.validate_against(state, "session.schema.json")))

    def test_migration_creates_a_linked_v2_checkpoint_without_inheriting_authority(self):
        source = reference()
        before = copy.deepcopy(source)

        result = migration.migrate_frame_axes(
            source,
            artifact_bytes(),
            checkpoint_id="ckpt_reference_v2_001",
            session_id="sess_reference_v2_001",
            prompt_identities=TARGET_PROMPTS,
            created_at="2026-09-09T15:00:00Z",
        )

        self.assertEqual(result["outcome"], "migrated", result)
        migrated = result["checkpoint"]
        self.assertEqual(source, before, "migration must not mutate its v1 source")
        self.assertEqual(migrated["id"], "ckpt_reference_v2_001")
        self.assertEqual(migrated["session_id"], "sess_reference_v2_001")
        self.assertEqual(migrated["schema_version"], "2.0.0")
        self.assertEqual(migrated["state"]["schema_version"], "2.0.0")
        self.assertEqual(migrated["source_checkpoint"], {
            "id": "ckpt_reference_001",
            "digest": "sha256:555789647f89bb17082d7623ffd31626647d27d199e4e82bd498cdf090ea107d",
            "schema_version": "1.0.0",
        })
        self.assertEqual(migrated["event_cursor"], 0)
        self.assertEqual(migrated["session_revision"], 0)
        self.assertIsNone(migrated["prior_checkpoint_digest"])
        self.assertEqual(migrated["state"]["revision"], 0)
        self.assertEqual(migrated["state"]["phase"], "framing")
        self.assertIsNone(migrated["state"]["active_frame_id"])
        self.assertEqual(migrated["state"]["approvals"], [])
        frame = migrated["state"]["frames"][0]
        self.assertEqual(frame["abstraction_level"], "product")
        self.assertEqual(frame["system_boundary"], "product")
        self.assertEqual(frame["status"], "proposed")
        self.assertNotEqual(frame["digest"], source["state"]["frames"][0]["digest"])
        self.assertEqual(schema.validate_against(migrated, "checkpoint.v2.schema.json"), [])
        self.assertEqual(checkpoint.verify(migrated, artifact_bytes()), [])

    def test_ambiguous_legacy_axes_require_human_review(self):
        source = reference()
        source["state"]["frames"][0]["abstraction_level"] = "supply_chain"
        source = checkpoint.encode(source)

        result = migration.migrate_frame_axes(
            source,
            artifact_bytes(),
            checkpoint_id="ckpt_ambiguous_v2_001",
            session_id="sess_ambiguous_v2_001",
            prompt_identities=TARGET_PROMPTS,
            created_at="2026-09-09T15:00:00Z",
        )

        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "approval_required")
        self.assertIsNone(result["checkpoint"])
        self.assertEqual(result["review_kind"], "frame_axis_mapping")
        self.assertEqual(result["reviews"], [{
            "frame_id": "frame_001",
            "legacy_abstraction_level": "supply_chain",
            "required_fields": ["abstraction_level", "system_boundary"],
        }])

    def test_unsupported_corrupt_or_identity_reusing_migrations_are_refused(self):
        unsupported = reference()
        unsupported["schema_version"] = "3.0.0"
        corrupt = reference()
        corrupt["state"]["title"] = "Changed without recomputing the source digest"

        cases = (
            (unsupported, "ckpt_v2_001", "sess_v2_001", "schema_invalid"),
            (corrupt, "ckpt_v2_001", "sess_v2_001", "checkpoint_integrity_failed"),
            (reference(), "ckpt_reference_001", "sess_v2_001", "invariant_violation"),
            (reference(), "ckpt_v2_001", "sess_reference_001", "invariant_violation"),
        )
        for source, checkpoint_id, session_id, code in cases:
            with self.subTest(code=code, checkpoint_id=checkpoint_id, session_id=session_id):
                result = migration.migrate_frame_axes(
                    source,
                    artifact_bytes(),
                    checkpoint_id=checkpoint_id,
                    session_id=session_id,
                    prompt_identities=TARGET_PROMPTS,
                    created_at="2026-09-09T15:00:00Z",
                )
                self.assertEqual(result["outcome"], "refused", result)
                self.assertEqual(result["code"], code)
                self.assertIsNone(result["checkpoint"])


if __name__ == "__main__":
    unittest.main()
