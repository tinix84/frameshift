"""Authorizing one brokered capability execution (#21, #24, ADR-0005).

#21's execution lifecycle has seven steps. Three of them need a runtime to
execute against and a policy store that does not exist yet. Four can be checked
from the request, the capability manifest, and the approval alone, and those are
here:

1. Validate the request and its input revision.
2. Resolve the capability against what the adapter actually offers.
4. Bind the approval to the request digest.
6. Validate and bound the output.

The binding in step 4 is the one worth reading twice. ADR-0002 binds a phase
approval to the *content* it approves; this binds a tool approval to the
*request* it authorizes. Without it, a human approving "read this file" could
have their signature spent on "send that file somewhere", because both are tool
requests from the same session at the same revision.

Everything a request declares — the destination, the data classes leaving, the
side effect, whether it can be undone — is there because an approver is agreeing
to those and not merely to an operation name. A request may not claim a weaker
approval requirement or a milder side effect than the capability's own manifest
declares, for the same reason #126 refuses a capability downgrade on restore.

Tool results are untrusted input, so `accept_result` checks shape and identity
and nothing else. There is deliberately nowhere in a tool result to put an
approval, a proposal, or an instruction.
"""

from __future__ import annotations

from frameshift.orchestration.transitions import APPROVAL_REQUIRED, APPROVAL_STALE
from frameshift.persistence import canonical
from frameshift.validation import validate_against

CAPABILITY_UNAVAILABLE = "capability_unavailable"
DATA_CLASS_NOT_ALLOWED = "data_class_not_allowed"
TOOL_POLICY_DENIED = "tool_policy_denied"
SCHEMA_INVALID = "schema_invalid"

REQUEST_SCHEMA = "tool-request.schema.json"
RESULT_SCHEMA = "tool-result.schema.json"

# Weakest gate first, least severe effect first — the same orderings the restore
# comparison uses, and for the same reason.
APPROVAL_STRENGTH = ("never", "policy", "each_call")
SIDE_EFFECT_SEVERITY = ("none", "reversible", "external", "irreversible")


def request_digest(request: dict) -> str:
    """The digest an approval binds to. Canonical, so formatting cannot change it."""
    return canonical.digest(request)


def _capability(capability_id: str, manifest: dict) -> dict | None:
    for item in manifest.get("capabilities", []):
        if isinstance(item, dict) and item.get("id") == capability_id:
            return item
    return None


def needs_approval(request: dict) -> bool:
    """Whether a human must sign this call before it runs."""
    return request.get("approval") == "each_call"


def authorize(request: dict, manifest: dict, approval: dict | None = None) -> list[str]:
    """Refusals for one tool request. An empty list means it may be executed."""
    invalid = validate_against(request, REQUEST_SCHEMA)
    if invalid:
        return [f"{SCHEMA_INVALID}: {item}" for item in invalid]

    refusals: list[str] = []
    capability = _capability(request["capability_id"], manifest)
    if capability is None or not capability.get("available"):
        return [
            f"{CAPABILITY_UNAVAILABLE}: {request['capability_id']} is not offered by this profile"
        ]

    if request["operation"] not in capability.get("operations", []):
        refusals.append(
            f"{TOOL_POLICY_DENIED}: operation {request['operation']!r} is not one of "
            f"{sorted(capability.get('operations', []))} for {request['capability_id']}"
        )

    # A request cannot ask for a looser gate than the capability declares. The
    # manifest is the ceiling, not a suggestion.
    declared, asked = capability.get("approval"), request["approval"]
    if declared in APPROVAL_STRENGTH and asked in APPROVAL_STRENGTH:
        if APPROVAL_STRENGTH.index(asked) < APPROVAL_STRENGTH.index(declared):
            refusals.append(
                f"{TOOL_POLICY_DENIED}: request asks for approval {asked!r} where "
                f"{request['capability_id']} declares {declared!r}"
            )

    declared_effect, asked_effect = capability.get("side_effect"), request["side_effect"]
    if declared_effect in SIDE_EFFECT_SEVERITY and asked_effect in SIDE_EFFECT_SEVERITY:
        if SIDE_EFFECT_SEVERITY.index(asked_effect) < SIDE_EFFECT_SEVERITY.index(declared_effect):
            refusals.append(
                f"{TOOL_POLICY_DENIED}: request claims side effect {asked_effect!r} where "
                f"{request['capability_id']} declares {declared_effect!r}"
            )

    # What leaves the session is what an approver is agreeing to, so it cannot
    # exceed what the capability says it accepts.
    accepted = set(capability.get("data_classes", []))
    leaving = set(request["data_classes"])
    if accepted and not leaving <= accepted:
        refusals.append(
            f"{DATA_CLASS_NOT_ALLOWED}: {sorted(leaving - accepted)} would be transmitted to "
            f"{request['capability_id']}, which accepts {sorted(accepted)}"
        )

    if needs_approval(request):
        if approval is None:
            refusals.append(f"{APPROVAL_REQUIRED}: {request['capability_id']} requires approval per call")
        elif approval.get("disposition") != "approved":
            refusals.append(f"{APPROVAL_REQUIRED}: disposition is {approval.get('disposition')!r}")
        elif approval.get("actor", {}).get("kind") != "human":
            refusals.append(
                f"{APPROVAL_REQUIRED}: actor kind {approval.get('actor', {}).get('kind')!r} cannot approve"
            )
        elif approval.get("target_digest") != request_digest(request):
            # The whole point of step 4: a signature spent on a different call.
            refusals.append(
                f"{APPROVAL_STALE}: approval is bound to {approval.get('target_digest')!r}, "
                f"and this request digests to {request_digest(request)}"
            )
    return refusals


def accept_result(request: dict, result: dict) -> list[str]:
    """Tool output is untrusted input: check its shape and who it answers, nothing more."""
    invalid = validate_against(result, RESULT_SCHEMA)
    refusals = [f"{SCHEMA_INVALID}: {item}" for item in invalid]
    if invalid:
        return refusals

    if result["request_id"] != request["request_id"]:
        refusals.append(
            f"{TOOL_POLICY_DENIED}: result answers request {result['request_id']!r}, "
            f"not {request['request_id']!r}"
        )
    if result["status"] == "succeeded" and not (result.get("output") or result.get("artifact")):
        refusals.append(
            f"{TOOL_POLICY_DENIED}: result succeeded and returned neither output nor an artifact"
        )
    return refusals
