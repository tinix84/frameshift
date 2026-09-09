"""Executable contract for trusted native-client confirmation (#205)."""

from __future__ import annotations

import copy


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
        "action": "accept",
        "content": {"disposition": "approved"},
    }
    accepted = workflow.complete(
        request["id"], native, attestation, confirmed_at="2026-09-09T10:01:00Z"
    )
    if accepted["outcome"] != "accepted":
        errors.append(f"native confirmation was {accepted['outcome']}: {accepted['detail']}")
    elif [item["type"] for item in accepted["events"]] != ["approval.recorded", "phase.changed"]:
        errors.append(f"native confirmation emitted unexpected events: {accepted['events']}")

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
