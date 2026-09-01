"""Binding a tool execution into one auditable record (#23 FR-11).

FR-11's acceptance signal names four things: tool request, result digest,
provenance, and authorization. All four existed separately after #149 and
nothing held them together, which is the state in which an audit trail is
technically present and practically useless — the auditor's question is never
"was there a digest", it is "what was asked, who allowed it, and what came
back".

Two properties make the record worth keeping rather than merely writing:

- The recorded request digest is recomputed from the request, so a record
  cannot describe a call that was never made.
- **A refused authorization cannot carry a result.** If something ran anyway,
  the record says so, and that is the single most important thing an audit of
  tool use can catch.
"""

from __future__ import annotations

from frameshift.broker.port import TOOL_POLICY_DENIED, request_digest
from frameshift.persistence import canonical
from frameshift.validation import validate_against

RECORD_SCHEMA = "tool-audit-record.schema.json"


def record(
    request: dict,
    refusals: list[str],
    recorded_at: str,
    result: dict | None = None,
    approval: dict | None = None,
) -> dict:
    """The audit record for one brokered call, allowed or refused."""
    entry = {
        "schema_version": "1.0.0",
        "request_id": request["request_id"],
        "request_digest": request_digest(request),
        "capability_id": request["capability_id"],
        "operation": request["operation"],
        "data_classes": list(request["data_classes"]),
        "authorization": {
            "outcome": "refused" if refusals else "allowed",
            "refusals": list(refusals),
        },
        "recorded_at": recorded_at,
    }
    if approval is not None:
        actor = approval.get("actor")
        if actor is not None:
            entry["authorization"]["approved_by"] = actor
        digest = approval.get("target_digest")
        if digest is not None:
            entry["authorization"]["approval_digest"] = digest
    if result is not None:
        entry["result_status"] = result["status"]
        if result.get("digest"):
            entry["result_digest"] = result["digest"]
        if result.get("provenance"):
            entry["provenance"] = result["provenance"]
    return entry


def record_violations(entry: dict, request: dict, result: dict | None = None) -> list[str]:
    """Whether this record faithfully describes the call it claims to."""
    violations = [f"schema_invalid: {item}" for item in validate_against(entry, RECORD_SCHEMA)]
    if violations:
        return violations

    if entry["request_digest"] != request_digest(request):
        violations.append(
            f"{TOOL_POLICY_DENIED}: the record's request_digest does not match the request it names"
        )

    refused = entry["authorization"]["outcome"] == "refused"
    if refused and ("result_digest" in entry or "result_status" in entry):
        # The one thing an audit of tool use exists to catch.
        violations.append(
            f"{TOOL_POLICY_DENIED}: the call was refused and the record carries a result — "
            "something executed that was not allowed to"
        )
    if not refused and result is not None and entry.get("result_digest") != result.get("digest"):
        violations.append(
            f"{TOOL_POLICY_DENIED}: the record's result_digest does not match the result it names"
        )

    signature = entry["authorization"].get("approval_digest")
    if signature is not None and signature != entry["request_digest"]:
        violations.append(
            f"{TOOL_POLICY_DENIED}: the recorded signature is bound to {signature}, "
            "not to the request it authorized"
        )
    return violations


def digest(entry: dict) -> str:
    """A digest of the record itself, so an audit trail can be checked for tampering."""
    return canonical.digest(entry)
