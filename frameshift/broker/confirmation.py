"""Bind trusted client confirmation to one exact pending proposal (#205)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from frameshift.validation import validate_against

from .port import request_digest as _canonical_digest

APPROVAL_REQUIRED = "approval_required"
APPROVAL_STALE = "approval_stale"
SCHEMA_INVALID = "schema_invalid"
UNSUPPORTED_CONFIGURATION = "unsupported_configuration"

_ISSUER = object()


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def approval_configuration_refusal(
    profile: dict,
    paths: list[Path],
    working_directory: Path,
) -> str | None:
    """A validated profile cannot be sourced from the agent-writable workspace."""
    if profile.get("validated") and any(
        _inside(path.resolve(), working_directory.resolve()) for path in paths
    ):
        return "validated approval configuration must be outside the agent-writable working directory"
    return None


def validated_approval_profile(
    baseline: dict,
    current: dict,
    configuration: dict,
    mcp_configuration: dict,
) -> dict:
    """Apply the supported native-client configuration policy to a loaded profile."""
    required_flags = {"--restricted", "--strict-mcp-config", "--tools="}
    valid = (
        current == baseline
        and current.get("config_digest") == _canonical_digest(configuration)
        and configuration.get("client_id") == current.get("client_id")
        and configuration.get("client_version") == current.get("client_version")
        and required_flags <= set(configuration.get("launch_flags", []))
        and configuration.get("mcp_config_digest") == _canonical_digest(mcp_configuration)
    )
    return dict(current, validated=bool(current.get("validated") and valid))


@dataclass(frozen=True)
class TrustedConfirmation:
    """Provider-neutral authority that cannot arrive through JSON tool input."""

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


def bind_confirmation_response(
    request: dict,
    response: dict,
    attestation: dict,
    profile: dict,
    *,
    authorized_roles: frozenset[str],
    confirmed_at: str,
) -> dict:
    """Return authority only for an exact, provider-neutral trusted response."""
    invalid = []
    for value, schema in (
        (request, "confirmation-request.schema.json"),
        (response, "confirmation-response.schema.json"),
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

    status = response["status"]
    if status in {"declined", "cancelled"}:
        return _pending(APPROVAL_REQUIRED, f"confirmation was {status}")

    disposition = response["disposition"]
    if disposition not in request["permitted_dispositions"]:
        return _pending(APPROVAL_REQUIRED, f"disposition is {disposition!r}")
    if disposition == "edited":
        edited = response["edited_proposal"]
        if not edited:
            return _pending(SCHEMA_INVALID, "edited disposition requires edited_proposal")
        return {
            "outcome": "revised",
            "code": APPROVAL_REQUIRED,
            "detail": "edited content requires a fresh confirmation",
            "edited_proposal": edited,
            "events": [],
        }
    if response["edited_proposal"] is not None:
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
