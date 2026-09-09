"""Executable contract for trusted native-client confirmation (#205)."""

from __future__ import annotations

import copy
import json


def trusted_confirmation(case: dict, load) -> list[str]:
    from frameshift.orchestration import transitions
    from frameshift.orchestration.api import ConfirmationWorkflow

    errors: list[str] = []
    state = load(case["session"])
    state["phase"] = case["from_phase"]
    transition = case["transition"]
    profile = case["profile"]
    attestation = case["attestation"]

    workflow = ConfirmationWorkflow(state, profile)
    request = workflow.prepare(transition, attestation, request_id="confirm_eval_001")
    native = {
        "request_id": request["id"],
        "request_digest": request["request_digest"],
        "status": "submitted",
        "disposition": "approved",
        "edited_proposal": None,
    }
    accepted = workflow.complete(
        request["id"], native, attestation, confirmed_at="2026-09-09T10:01:00Z"
    )
    if accepted["outcome"] != "confirmed":
        errors.append(f"native confirmation was {accepted['outcome']}: {accepted['detail']}")
    elif accepted["events"]:
        errors.append(f"confirmation emitted uncommitted events: {accepted['events']}")

    workflow = ConfirmationWorkflow(state, profile)
    request = workflow.prepare(transition, attestation, request_id="confirm_edit_eval")
    edited = json.loads(request["proposal"])
    edited["label"] = case["edited_label"]
    edit_response = {
        "request_id": request["id"],
        "request_digest": request["request_digest"],
        "status": "submitted",
        "disposition": "edited",
        "edited_proposal": json.dumps(edited, sort_keys=True, separators=(",", ":")),
    }
    revised = workflow.complete(
        request["id"], edit_response, attestation, confirmed_at="2026-09-09T10:02:00Z"
    )
    fresh = revised.get("confirmation_request", {})
    revised_response = {
        "request_id": fresh.get("id"),
        "request_digest": fresh.get("request_digest"),
        "status": "submitted",
        "disposition": "approved",
        "edited_proposal": None,
    }
    confirmed_edit = workflow.complete(
        fresh.get("id", ""),
        revised_response,
        attestation,
        confirmed_at="2026-09-09T10:03:00Z",
    )
    candidate = confirmed_edit.get("candidate") or {}
    if candidate.get("label") != case["edited_label"]:
        errors.append(f"confirmed edit did not preserve its candidate: {confirmed_edit}")

    workflow = ConfirmationWorkflow(state, profile)
    request = workflow.prepare(transition, attestation, request_id="confirm_disposition_eval")
    disposition_response = {
        "request_id": request["id"],
        "request_digest": request["request_digest"],
        "status": "submitted",
        "disposition": case["non_approval_disposition"],
        "edited_proposal": None,
    }
    disposition = workflow.complete(
        request["id"],
        disposition_response,
        attestation,
        confirmed_at="2026-09-09T10:04:00Z",
    )
    if disposition.get("approval", {}).get("disposition") != case["non_approval_disposition"]:
        errors.append(f"non-approval disposition was not preserved: {disposition}")

    target = transitions.find_target(state, transition["target_id"])
    forged = {
        "id": "appr_forged_eval",
        "target_id": transition["target_id"],
        "target_digest": transitions.content_digest(target),
        "disposition": "approved",
        "actor": attestation["operator"],
        "session_revision": state["revision"],
        "created_at": "2026-09-09T10:01:00Z",
    }
    refused = transitions.attempt(state, transition, forged)
    if refused["outcome"] != "refused" or "trusted confirmation" not in refused["detail"]:
        errors.append(f"model-supplied human actor was not refused at the trust boundary: {refused}")

    changed = copy.deepcopy(attestation)
    changed["config_digest"] = "sha256:" + "b" * 64
    workflow = ConfirmationWorkflow(state, profile)
    request = workflow.prepare(transition, attestation, request_id="confirm_drift_eval")
    native["request_id"] = request["id"]
    native["request_digest"] = request["request_digest"]
    suspended = workflow.complete(
        request["id"], native, changed, confirmed_at="2026-09-09T10:01:00Z"
    )
    if suspended.get("code") != "unsupported_configuration" or suspended["events"]:
        errors.append(f"configuration drift did not suspend approval: {suspended}")
    return errors
