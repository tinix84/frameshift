"""Named synthetic refusal corpus for the capability broker."""
from __future__ import annotations

import copy

from frameshift.broker import execute
from frameshift.broker.audit import record_violations
from frameshift.broker.confirmation import bind_native_response, build_request


def _trusted_native(approval: dict | None, request: dict):
    if approval is None:
        return None
    actor = approval["actor"]
    pending = build_request(
        request_id=f"confirm_{approval['id']}",
        session_id="sess_broker_eval",
        session_revision=approval["session_revision"],
        gate="capability_execution",
        target_id=approval["target_id"],
        target_digest=approval["target_digest"],
        proposal="{}",
        actor=actor,
    )
    profile = {
        "schema_version": "1.0.0",
        "id": "profile_broker_eval",
        "client_id": "claude-code",
        "client_version": "2.1.265",
        "config_digest": "sha256:" + "a" * 64,
        "validated": True,
    }
    attestation = {
        "schema_version": "1.0.0",
        "profile_id": profile["id"],
        "client_id": profile["client_id"],
        "client_version": profile["client_version"],
        "config_digest": profile["config_digest"],
        "operator": actor,
        "attested_at": "2026-07-15T09:13:00Z",
    }
    native = {
        "request_id": pending["id"],
        "request_digest": pending["request_digest"],
        "action": "accept",
        "content": {"disposition": approval["disposition"]},
    }
    return bind_native_response(
        pending,
        native,
        attestation,
        profile,
        authorized_roles=frozenset({actor.get("role")}),
        confirmed_at=approval["created_at"],
    ).get("confirmation")


def broker_refusal(case: dict, load) -> list[str]:
    request = load(case["request"])
    request.update(case.get("request_updates", {}))
    manifest = load(case["manifest"])
    calls: list[dict] = []
    result = load(case["result"]) if case.get("result") else None
    original_result = copy.deepcopy(result)

    def executor(value):
        calls.append(value)
        if case.get("executor_raises"):
            raise RuntimeError("synthetic executor failure")
        return result

    approval = case.get("approval")
    if case.get("approval_is_trusted_native"):
        approval = _trusted_native(approval, request)
    retry_approval = case.get("retry_approval")
    if case.get("retry_approval_is_trusted_native"):
        retry_approval = _trusted_native(retry_approval, request)

    outcome = execute(
        request, manifest, executor,
        approval=approval,
        retry_approval=retry_approval,
        prior_requests=copy.deepcopy(case.get("prior_requests")),
        recorded_at="2026-07-15T09:14:00Z",
    )
    errors = []
    if outcome["status"] != case["expect_status"]:
        errors.append(f"expected {case['expect_status']}, got {outcome['status']}")
    if len(calls) != case.get("expect_calls", 0):
        errors.append(f"expected {case.get('expect_calls', 0)} executor calls, got {len(calls)}")
    for text in case.get("reason_contains", []):
        if text not in outcome.get("denied_reason", ""):
            errors.append(f"denial does not contain {text!r}")
    if case.get("expect_alternatives") and not outcome.get("alternatives"):
        errors.append("unavailable capability returned no alternatives")
    audit = outcome.get("audit")
    if case.get("expect_audit_fields"):
        for field in case["expect_audit_fields"]:
            if field not in (audit or {}):
                errors.append(f"audit missing {field}")
    if audit:
        errors.extend(record_violations(audit, request, result if calls and "execution_error" not in audit else None))
    if case.get("expect_audit_fields") and calls:
        for field in ("capability_id", "operation", "data_classes", "destination"):
            if (audit or {}).get(field) != request.get(field):
                errors.append(f"audit {field} does not match the executed request")
        if (audit or {}).get("result_digest") != (result.get("digest") if isinstance(result, dict) else None):
            errors.append("audit result digest does not match the returned evidence")
    if case.get("expect_untrusted_output"):
        if outcome.get("result") != original_result or result != original_result:
            errors.append("tool evidence was not preserved as inert output")
        if any(key in outcome for key in ("approvals", "proposals", "instructions")):
            errors.append("tool output gained an authority-bearing field")
        if (audit or {}).get("authorization", {}).get("approved_by") is not None:
            errors.append("tool output fabricated an approving actor")
    return errors
