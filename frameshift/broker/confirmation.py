"""Bind a native client confirmation to one exact pending proposal (#205)."""

from __future__ import annotations

from dataclasses import dataclass
import json

from frameshift.validation import validate_against

from .port import request_digest as _canonical_digest

APPROVAL_REQUIRED = "approval_required"
APPROVAL_STALE = "approval_stale"
SCHEMA_INVALID = "schema_invalid"
UNSUPPORTED_CONFIGURATION = "unsupported_configuration"

_ISSUER = object()


@dataclass(frozen=True)
class TrustedConfirmation:
    """An in-process authority value that cannot arrive through JSON tool input."""

    _approval_json: bytes
    _issuer: object

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise ValueError("trusted confirmations are issued only by the confirmation broker")

    @property
    def approval(self) -> dict:
        return json.loads(self._approval_json)


def request_digest(request: dict) -> str:
    """Digest a request without its self-describing digest field."""
    return _canonical_digest({key: value for key, value in request.items() if key != "request_digest"})


def build_request(
    *,
    request_id: str,
    session_id: str,
    session_revision: int,
    gate: str,
    target_id: str,
    target_digest: str,
    proposal: str,
    actor: dict,
) -> dict:
    """Build the exact, provider-neutral content a client must display."""
    request = {
        "schema_version": "1.0.0",
        "id": request_id,
        "session_id": session_id,
        "session_revision": session_revision,
        "gate": gate,
        "target_id": target_id,
        "target_digest": target_digest,
        "proposal": proposal,
        "actor": dict(actor),
        "permitted_dispositions": [
            "approved",
            "edited",
            "rejected",
            "deferred",
            "evidence_requested",
        ],
    }
    request["request_digest"] = request_digest(request)
    violations = validate_against(request, "confirmation-request.schema.json")
    if violations:
        raise ValueError("invalid confirmation request: " + "; ".join(violations))
    return request


def bind_native_response(
    request: dict,
    response: dict,
    attestation: dict,
    profile: dict,
    *,
    authorized_roles: frozenset[str],
    confirmed_at: str,
) -> dict:
    """Return a trusted authority value only for an exact supported response."""
    invalid = []
    for value, schema in (
        (request, "confirmation-request.schema.json"),
        (response, "native-confirmation-response.schema.json"),
        (attestation, "operator-attestation.schema.json"),
        (profile, "approval-profile.schema.json"),
    ):
        invalid.extend(validate_against(value, schema))
    if invalid:
        return _pending(SCHEMA_INVALID, "; ".join(invalid))

    if not profile["validated"]:
        return _pending(UNSUPPORTED_CONFIGURATION, "approval profile has not passed actual-client validation")
    for field in ("profile_id", "client_id", "client_version", "config_digest"):
        expected = profile["id"] if field == "profile_id" else profile[field]
        if attestation[field] != expected:
            return _pending(
                UNSUPPORTED_CONFIGURATION,
                f"attested {field} no longer matches the validated approval profile",
            )

    if response["request_id"] != request["id"]:
        return _pending(APPROVAL_STALE, "native response belongs to another confirmation request")
    if response["request_digest"] != request["request_digest"]:
        return _pending(APPROVAL_STALE, "native response does not bind the displayed request digest")
    if request_digest(request) != request["request_digest"]:
        return _pending(APPROVAL_STALE, "pending confirmation request changed after it was prepared")

    action = response["action"]
    if action in {"decline", "cancel"}:
        return _pending(APPROVAL_REQUIRED, f"native dialog action was {action}")

    content = response.get("content") or {}
    disposition = content.get("disposition")
    if disposition not in request["permitted_dispositions"]:
        return _pending(APPROVAL_REQUIRED, f"disposition is {disposition!r}")
    if disposition == "edited":
        edited = content.get("edited_proposal")
        if not edited:
            return _pending(SCHEMA_INVALID, "edited disposition requires edited_proposal")
        return {
            "outcome": "revised",
            "code": APPROVAL_REQUIRED,
            "detail": "edited content requires a fresh confirmation",
            "edited_proposal": edited,
            "events": [],
        }
    if "edited_proposal" in content:
        return _pending(SCHEMA_INVALID, "edited_proposal is permitted only with disposition edited")
    actor = attestation["operator"]
    if actor["kind"] != "human":
        return _pending(APPROVAL_REQUIRED, "operator attestation does not name a human")
    if actor.get("role") not in authorized_roles:
        return _pending(APPROVAL_REQUIRED, f"actor role {actor.get('role')} lacks authority for {request['gate']}")
    if actor != request["actor"]:
        return _pending(APPROVAL_STALE, "attested operator differs from the displayed actor authority")

    approval = {
        "id": f"appr_{request['id']}",
        "target_id": request["target_id"],
        "target_digest": request["target_digest"],
        "disposition": disposition,
        "actor": dict(actor),
        "session_revision": request["session_revision"],
        "created_at": confirmed_at,
    }
    invalid_approval = validate_against(approval, "approval.schema.json")
    if invalid_approval:
        return _pending(SCHEMA_INVALID, "; ".join(invalid_approval))
    return {
        "outcome": "confirmed",
        "code": None,
        "detail": "",
        "confirmation": TrustedConfirmation(
            json.dumps(approval, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            _ISSUER,
        ),
        "events": [],
    }


def _pending(code: str, detail: str) -> dict:
    return {"outcome": "pending", "code": code, "detail": detail, "events": []}
