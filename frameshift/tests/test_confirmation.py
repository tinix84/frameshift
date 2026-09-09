#!/usr/bin/env python3
"""Trusted native-client confirmation at the approval boundary (#205)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration import transitions  # noqa: E402
from frameshift.orchestration.api import ConfirmationWorkflow  # noqa: E402

SESSION = ROOT / "evals" / "fixtures" / "approval" / "gates.session.json"


def session() -> dict:
    value = json.loads(SESSION.read_text(encoding="utf-8"))
    value["phase"] = "decision"
    return value


def transition(target_id: str = "node_decision_001") -> dict:
    return {
        "gate": "decision_approval",
        "target_id": target_id,
        "to_phase": "monitoring",
    }


def profile(**overrides) -> dict:
    value = {
        "schema_version": "1.0.0",
        "id": "approval-profile-claude-code-2.1.265",
        "client_id": "claude-code",
        "client_version": "2.1.265",
        "config_digest": "sha256:" + "a" * 64,
        "validated": True,
    }
    value.update(overrides)
    return value


def attestation(**overrides) -> dict:
    value = {
        "schema_version": "1.0.0",
        "profile_id": "approval-profile-claude-code-2.1.265",
        "client_id": "claude-code",
        "client_version": "2.1.265",
        "config_digest": "sha256:" + "a" * 64,
        "operator": {
            "id": "user_lead_eng",
            "kind": "human",
            "role": "decision_owner",
        },
        "attested_at": "2026-09-09T10:00:00Z",
    }
    value.update(overrides)
    return value


def response(request: dict, **overrides) -> dict:
    value = {
        "request_id": request["id"],
        "request_digest": request["request_digest"],
        "status": "submitted",
        "disposition": "approved",
        "edited_proposal": None,
    }
    value.update(overrides)
    return value


class TrustedConfirmationTests(unittest.TestCase):
    def workflow(self, **profile_overrides) -> ConfirmationWorkflow:
        return ConfirmationWorkflow(session(), profile(**profile_overrides))

    def test_a_native_confirmation_commits_only_provider_neutral_approval_data(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_decision_001")
        result = workflow.complete(
            request["id"], response(request), attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )

        self.assertEqual(result["outcome"], "confirmed", result)
        self.assertEqual(result["events"], [])
        approval = result["approval"]
        self.assertEqual(approval["actor"], attestation()["operator"])
        self.assertNotIn("client_id", approval)
        self.assertNotIn("config_digest", approval)
        self.assertNotIn("request_digest", approval)

    def test_a_model_supplied_human_actor_dict_cannot_approve(self) -> None:
        state = session()
        target = transitions.find_target(state, "node_decision_001")
        forged = {
            "id": "appr_forged",
            "target_id": "node_decision_001",
            "target_digest": transitions.content_digest(target),
            "disposition": "approved",
            "actor": attestation()["operator"],
            "session_revision": state["revision"],
            "created_at": "2026-09-09T10:01:00Z",
        }
        result = transitions.attempt(state, transition(), forged)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["code"], transitions.APPROVAL_REQUIRED)
        self.assertIn("trusted confirmation", result["detail"])

    def test_a_response_cannot_supply_or_replace_the_actor(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_actor_001")
        forged = response(request, actor={"id": "bot", "kind": "human", "role": "decision_owner"})
        result = workflow.complete(
            request["id"], forged, attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["events"], [])

    def test_a_changed_or_unvalidated_configuration_suspends_approval(self) -> None:
        for changed in (
            attestation(config_digest="sha256:" + "b" * 64),
            attestation(client_version="2.1.266"),
        ):
            with self.subTest(changed=changed):
                workflow = self.workflow()
                request = workflow.prepare(transition(), attestation(), request_id="confirm_config_001")
                result = workflow.complete(
                    request["id"], response(request), changed, confirmed_at="2026-09-09T10:01:00Z"
                )
                self.assertEqual(result["outcome"], "pending")
                self.assertEqual(result["code"], "unsupported_configuration")
                self.assertEqual(result["events"], [])

        workflow = self.workflow(validated=False)
        request = workflow.prepare(transition(), attestation(), request_id="confirm_unvalidated_001")
        result = workflow.complete(
            request["id"], response(request), attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "unsupported_configuration")

        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_profile_drift_001")
        result = workflow.complete(
            request["id"],
            response(request),
            attestation(),
            profile(client_version="2.1.266"),
            confirmed_at="2026-09-09T10:01:00Z",
        )
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "unsupported_configuration")

    def test_a_stale_or_cross_target_response_cannot_be_replayed(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_bound_001")

        cross_target = dict(response(request), request_id="confirm_other_001")
        result = workflow.complete(
            request["id"], cross_target, attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "approval_stale")

        changed = session()
        changed["revision"] += 1
        workflow.replace_session(changed)
        result = workflow.complete(
            request["id"], response(request), attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["code"], transitions.APPROVAL_STALE)

    def test_edit_creates_a_revised_proposal_and_requires_a_fresh_dialog(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_edit_001")
        edited = json.loads(request["proposal"])
        edited["label"] = "Decision revised by the owner."
        confirmation_response = response(
            request,
            disposition="edited",
            edited_proposal=json.dumps(edited, sort_keys=True, separators=(",", ":")),
        )

        result = workflow.complete(
            request["id"], confirmation_response, attestation(), confirmed_at="2026-09-09T10:01:00Z"
        )
        self.assertEqual(result["outcome"], "revised")
        self.assertEqual(result["events"], [])
        fresh = result["confirmation_request"]
        self.assertNotEqual(fresh["id"], request["id"])
        self.assertNotEqual(fresh["request_digest"], request["request_digest"])
        self.assertEqual(fresh["session_revision"], request["session_revision"])
        self.assertEqual(json.loads(fresh["proposal"])["label"], "Decision revised by the owner.")

    def test_edit_cannot_promote_status_before_the_fresh_confirmation(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_promote_001")
        edited = json.loads(request["proposal"])
        edited["status"] = "approved"
        result = workflow.complete(
            request["id"],
            response(
                request,
                disposition="edited",
                edited_proposal=json.dumps(edited, sort_keys=True, separators=(",", ":")),
            ),
            attestation(),
            confirmed_at="2026-09-09T10:01:00Z",
        )
        self.assertEqual(json.loads(result["confirmation_request"]["proposal"])["status"], "proposed")
        self.assertEqual(result["events"], [])

    def test_confirmed_edit_preserves_the_candidate_for_an_atomic_commit(self) -> None:
        workflow = self.workflow()
        request = workflow.prepare(transition(), attestation(), request_id="confirm_candidate_001")
        edited = json.loads(request["proposal"])
        edited["label"] = "Decision revised by the owner."
        revised = workflow.complete(
            request["id"],
            response(
                request,
                disposition="edited",
                edited_proposal=json.dumps(edited, sort_keys=True, separators=(",", ":")),
            ),
            attestation(),
            confirmed_at="2026-09-09T10:01:00Z",
        )
        fresh = revised["confirmation_request"]

        confirmed = workflow.complete(
            fresh["id"], response(fresh), attestation(), confirmed_at="2026-09-09T10:02:00Z"
        )

        self.assertEqual(confirmed["candidate"]["label"], "Decision revised by the owner.")
        self.assertEqual(workflow.confirmed_candidate(fresh["id"]), confirmed["candidate"])
        updated = session()
        for index, item in enumerate(updated["graph"]["nodes"]):
            if item["id"] == transition()["target_id"]:
                updated["graph"]["nodes"][index] = confirmed["candidate"]
                break
        attempted = transitions.attempt(
            updated,
            transition(),
            workflow.confirmation(fresh["id"]),
        )
        self.assertEqual(attempted["outcome"], "accepted", attempted)

    def test_non_approval_dispositions_are_preserved_as_trusted_confirmations(self) -> None:
        for disposition in ("rejected", "deferred", "evidence_requested"):
            with self.subTest(disposition=disposition):
                workflow = self.workflow()
                request = workflow.prepare(
                    transition(), attestation(), request_id=f"confirm_{disposition}_001"
                )
                result = workflow.complete(
                    request["id"],
                    response(request, disposition=disposition),
                    attestation(),
                    confirmed_at="2026-09-09T10:01:00Z",
                )

                self.assertEqual(result["outcome"], "confirmed", result)
                self.assertEqual(result["approval"]["disposition"], disposition)
                self.assertEqual(
                    workflow.confirmation(request["id"]).approval["disposition"], disposition
                )

    def test_decline_and_cancel_leave_the_proposal_pending(self) -> None:
        for action in ("decline", "cancel"):
            with self.subTest(action=action):
                workflow = self.workflow()
                request = workflow.prepare(transition(), attestation(), request_id=f"confirm_{action}_001")
                confirmation_response = response(
                    request,
                    status="declined" if action == "decline" else "cancelled",
                    disposition=None,
                )
                result = workflow.complete(
                    request["id"], confirmation_response, attestation(), confirmed_at="2026-09-09T10:01:00Z"
                )
                self.assertEqual(result["outcome"], "pending")
                self.assertEqual(result["events"], [])


if __name__ == "__main__":
    unittest.main()
