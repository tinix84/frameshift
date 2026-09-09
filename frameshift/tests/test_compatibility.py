#!/usr/bin/env python3
"""Tests for contract compatibility on restore (#22 step 6).

A checkpoint pins the prompt contracts it was produced under. Restore it
somewhere those prompts have been deleted, renamed, or rewritten and its
proposals cite reasoning nobody can reproduce. These prove each of those three
is noticed, and that a compatible checkpoint stays quiet.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import installed_prompt_manifests, restore_checkpoint  # noqa: E402
from frameshift.broker.confirmation import bind_confirmation_response, build_request  # noqa: E402
from frameshift.broker.port import request_digest  # noqa: E402
from frameshift.persistence import compatibility  # noqa: E402

REFERENCE = ROOT / "evals" / "fixtures" / "reference.checkpoint.json"
PROMPT_IDENTITY = ROOT / "evals" / "fixtures" / "prompt-identity.checkpoint.v2.json"

APPROVAL_PROFILE = {
    "schema_version": "1.0.0",
    "id": "approval-profile-prompt-change",
    "client_id": "test-client",
    "client_version": "1.0.0",
    "config_digest": "sha256:" + "a" * 64,
    "validated": True,
}


def installed() -> dict[str, dict]:
    return installed_prompt_manifests(ROOT / "prompts")


def checkpoint() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def prompt_identity_checkpoint() -> dict:
    return json.loads(PROMPT_IDENTITY.read_text(encoding="utf-8"))


def artifacts(cp: dict) -> dict[str, bytes]:
    return {
        item["id"]: (ROOT / item["uri"]).read_bytes().replace(b"\r\n", b"\n")
        for item in cp.get("artifacts", [])
    }


def prompt_change_confirmations(cp: dict) -> list:
    confirmed = []
    for change in cp.get("prompt_version_changes", []):
        attestation = {
            "schema_version": "1.0.0",
            "profile_id": APPROVAL_PROFILE["id"],
            "client_id": APPROVAL_PROFILE["client_id"],
            "client_version": APPROVAL_PROFILE["client_version"],
            "config_digest": APPROVAL_PROFILE["config_digest"],
            "operator": change["actor"],
            "attested_at": change["created_at"],
        }
        request = build_request(
            request_id=f"confirm_{change['id']}",
            session_id=cp["session_id"],
            session_revision=change["session_revision"],
            gate="decision_approval",
            target_id=change["id"],
            target_digest=request_digest(change),
            proposal=json.dumps(change, sort_keys=True, separators=(",", ":")),
            actor=change["actor"],
        )
        response = {
            "request_id": request["id"],
            "request_digest": request["request_digest"],
            "status": "submitted",
            "disposition": "approved",
            "edited_proposal": None,
        }
        outcome = bind_confirmation_response(
            request,
            response,
            attestation,
            APPROVAL_PROFILE,
            authorized_roles=frozenset({change["actor"]["role"]}),
            confirmed_at=change["created_at"],
        )
        confirmed.append(outcome["confirmation"])
    return confirmed


class InstalledPromptTests(unittest.TestCase):
    def test_all_committed_prompt_versions_are_found(self) -> None:
        manifests = installed()
        self.assertEqual(
            set(manifests),
            {
                "frameshift.problem-framing.v1",
                "frameshift.problem-framing.v2",
                "frameshift.repair-structured-output.v1",
                "frameshift.repair-structured-output.v2",
            },
        )

    def test_each_carries_its_declared_and_actual_digest(self) -> None:
        for identifier, manifest in installed().items():
            with self.subTest(prompt=identifier):
                self.assertEqual(manifest["body_digest"], manifest["actual_body_digest"])


class CompatibilityTests(unittest.TestCase):
    def test_an_exact_published_checkpoint_identity_allows_new_reasoning(self) -> None:
        from frameshift.bootstrap import published_identities

        value = prompt_identity_checkpoint()
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
            prompt_change_confirmations=prompt_change_confirmations(value),
        )
        self.assertEqual(plan["outcome"], "verified")
        self.assertTrue(plan["reasoning_allowed"], plan["contract_differences"])

    def test_a_missing_prompt_stays_inspectable_but_blocks_new_reasoning(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        value["contracts"]["prompts"]["problem_framing"]["id"] = "frameshift.missing.v2"
        value = checkpoint_port.encode(value)
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertEqual(plan["outcome"], "verified")
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("missing" in item for item in plan["contract_differences"]))

    def test_an_unapproved_recorded_version_change_blocks_new_reasoning(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        value["prompt_version_changes"] = []
        value = checkpoint_port.encode(value)
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("version-change approval" in item for item in plan["contract_differences"]))

    def test_a_recorded_human_actor_field_alone_does_not_grant_authority(self) -> None:
        from frameshift.bootstrap import published_identities

        plan = restore_checkpoint(
            prompt_identity_checkpoint(),
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("trusted confirmation" in item for item in plan["authorization_refusals"]))

    def test_bare_change_ids_cannot_grant_prompt_change_authority(self) -> None:
        from frameshift.bootstrap import published_identities

        plan = restore_checkpoint(
            prompt_identity_checkpoint(),
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
            prompt_change_confirmations=["prompt_change_001"],
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("trusted confirmation" in item for item in plan["authorization_refusals"]))

    def test_prompt_change_confirmation_must_bind_the_exact_change(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        stale = prompt_change_confirmations(value)
        value["prompt_version_changes"][0]["rationale"] = "Different approved content."
        value = checkpoint_port.encode(value)
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
            prompt_change_confirmations=stale,
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("exact change" in item for item in plan["authorization_refusals"]))

    def test_a_required_engine_without_a_prompt_pin_blocks_new_reasoning(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        value["contracts"]["prompts"] = {}
        value = checkpoint_port.encode(value)
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("has no prompt identity" in item for item in plan["contract_differences"]))

    def test_a_recorded_change_requires_confirmation_without_an_earlier_execution(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        value["execution_summaries"] = [value["execution_summaries"][-1]]
        value = checkpoint_port.encode(value)
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("trusted confirmation" in item for item in plan["authorization_refusals"]))

    def test_sequential_confirmed_version_changes_allow_new_reasoning(self) -> None:
        from frameshift.bootstrap import published_identities
        from frameshift.persistence import checkpoint as checkpoint_port

        value = prompt_identity_checkpoint()
        v2 = value["contracts"]["prompts"]["problem_framing"]
        v3 = {
            "id": "frameshift.problem-framing.v3",
            "version": "3.0.0",
            "digest": "sha256:" + "3" * 64,
        }
        value["contracts"]["prompts"]["problem_framing"] = v3
        value["execution_summaries"].append(
            {"execution_id": "exec_prompt_v3_001", "engine": "problem_framing", "prompt_contract": v3}
        )
        value["prompt_version_changes"].append(
            {
                "id": "prompt_change_002",
                "engine": "problem_framing",
                "from": v2,
                "to": v3,
                "actor": {"id": "user_owner", "kind": "human", "role": "decision_owner"},
                "session_revision": 2,
                "created_at": "2026-09-09T12:02:00Z",
            }
        )
        value = checkpoint_port.encode(value)
        manifests = installed()
        manifests[v3["id"]] = {
            **v3,
            "engine": "problem_framing",
            "body_digest": v3["digest"],
            "actual_body_digest": v3["digest"],
        }
        published = published_identities(ROOT / "prompts" / "releases")
        published.append({"id": v3["id"], "version": v3["version"], "body_digest": v3["digest"]})
        plan = restore_checkpoint(
            value,
            {},
            installed_prompts=manifests,
            published_prompts=published,
            prompt_change_confirmations=prompt_change_confirmations(value),
        )
        self.assertTrue(plan["reasoning_allowed"], plan)

    def test_the_committed_checkpoint_is_compatible(self) -> None:
        self.assertEqual(compatibility.contract_differences(checkpoint(), installed()), [])

    def test_a_pinned_prompt_that_is_not_installed_is_reported(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        differences = compatibility.contract_differences(cp, installed())
        self.assertTrue(any("frameshift.deleted.v1" in item for item in differences), differences)
        self.assertTrue(any("cannot be reproduced" in item for item in differences))

    def test_a_prompt_pinned_for_the_wrong_engine_is_reported(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["causal_reasoning"] = "frameshift.problem-framing.v1"
        differences = compatibility.contract_differences(cp, installed())
        self.assertTrue(any("declares engine" in item for item in differences), differences)

    def test_a_shared_prompt_may_be_pinned_for_any_engine(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["causal_reasoning"] = "frameshift.repair-structured-output.v1"
        self.assertEqual(compatibility.contract_differences(cp, installed()), [])

    def test_a_rewritten_prompt_is_reported(self) -> None:
        """Detectable only because a manifest digests its own body (#144)."""
        manifests = installed()
        tampered = copy.deepcopy(manifests)
        tampered["frameshift.problem-framing.v1"]["actual_body_digest"] = "sha256:" + "0" * 64
        differences = compatibility.contract_differences(checkpoint(), tampered)
        self.assertTrue(any("has been rewritten" in item for item in differences), differences)

    def test_a_checkpoint_pinning_nothing_reports_missing_engine_contracts(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"] = {}
        self.assertTrue(compatibility.contract_differences(cp, installed()))

    def test_differences_are_reports_and_carry_no_error_code(self) -> None:
        """#126's precedent: a difference is described, only a refusal is coded."""
        sys.path.insert(0, str(ROOT))
        from evals.checks import errors

        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        for item in compatibility.contract_differences(cp, installed()):
            first = item.split(":", 1)[0]
            self.assertNotIn(first, errors.VOCABULARY, "a report must not look like a refusal")


class RestorePlanTests(unittest.TestCase):
    def test_the_plan_blocks_reasoning_without_a_published_registry(self) -> None:
        cp = checkpoint()
        plan = restore_checkpoint(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "verified")
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("registry" in item for item in plan["contract_differences"]))

    def test_a_legacy_prompt_pin_is_inspectable_but_not_rerunnable(self) -> None:
        from frameshift.bootstrap import published_identities

        cp = checkpoint()
        plan = restore_checkpoint(
            cp,
            artifacts(cp),
            installed_prompts=installed(),
            published_prompts=published_identities(ROOT / "prompts" / "releases"),
        )
        self.assertEqual(plan["outcome"], "verified")
        self.assertFalse(plan["reasoning_allowed"])
        self.assertTrue(any("exact version and digest" in item for item in plan["contract_differences"]))

    def test_an_incompatible_checkpoint_still_restores(self) -> None:
        """What is lost is the ability to re-run, not the ability to read."""
        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        # Re-encode so the digests still match the edited envelope.
        from frameshift.persistence import encode

        cp = encode(cp)
        plan = restore_checkpoint(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "verified")
        self.assertTrue(plan["contract_differences"])
        self.assertTrue(plan["pending_proposal_ids"])

    def test_a_refused_restore_reports_no_differences(self) -> None:
        cp = checkpoint()
        cp["state"]["title"] = "tampered"
        plan = restore_checkpoint(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "refused")
        self.assertEqual(plan["contract_differences"], [])


if __name__ == "__main__":
    unittest.main()
