"""Named synthetic refusal corpus for the capability broker."""
from __future__ import annotations

import copy

from frameshift.broker import execute
from frameshift.broker.audit import record_violations


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

    outcome = execute(
        request, manifest, executor,
        approval=case.get("approval"),
        retry_approval=case.get("retry_approval"),
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
