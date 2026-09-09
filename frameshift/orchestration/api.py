"""Provider-neutral application operation for trusted confirmation (#205)."""

from __future__ import annotations

import copy
import json

from frameshift.broker.confirmation import bind_confirmation_response, build_request
from frameshift.validation import validate_against

from . import transitions


class ConfirmationWorkflow:
    """Hold pending confirmations for an independently executable vertical slice."""

    def __init__(self, session: dict, approval_profile: dict) -> None:
        self._session = copy.deepcopy(session)
        self._profile = copy.deepcopy(approval_profile)
        self._pending: dict[str, tuple[dict, dict, dict | None, int]] = {}
        self._confirmed = {}
        self._confirmed_candidates: dict[str, dict] = {}

    def replace_session(self, session: dict) -> None:
        """Supply current state as persistence will do when #172 connects this API."""
        self._session = copy.deepcopy(session)

    def prepare(self, transition: dict, attestation: dict, *, request_id: str) -> dict:
        target = transitions.find_target(self._session, transition["target_id"])
        if target is None:
            raise ValueError(f"no such target {transition['target_id']}")
        actor = attestation.get("operator", {})
        request = build_request(
            request_id=request_id,
            session_id=self._session["id"],
            session_revision=self._session["revision"],
            gate=transition["gate"],
            target_id=transition["target_id"],
            target_digest=transitions.content_digest(target),
            proposal=json.dumps(target, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            actor=actor,
        )
        self._pending[request_id] = (
            request,
            dict(transition),
            None,
            self._session["revision"],
        )
        return copy.deepcopy(request)

    def pending(self, request_id: str) -> dict | None:
        entry = self._pending.get(request_id)
        return copy.deepcopy(entry[0]) if entry else None

    def complete(
        self,
        request_id: str,
        response: dict,
        attestation: dict,
        current_profile: dict | None = None,
        *,
        confirmed_at: str,
    ) -> dict:
        entry = self._pending.get(request_id)
        if entry is None:
            return {
                "outcome": "pending",
                "code": "approval_stale",
                "detail": "no such pending confirmation request",
                "events": [],
            }
        request, transition, candidate, base_revision = entry
        if current_profile is not None and current_profile != self._profile:
            return {
                "outcome": "pending",
                "code": "unsupported_configuration",
                "detail": "approval profile changed after session start",
                "events": [],
            }
        gate = transition["gate"]
        roles = transitions.GATE_AUTHORITY.get(gate, frozenset())
        bound = bind_confirmation_response(
            request,
            response,
            attestation,
            self._profile,
            authorized_roles=roles,
            confirmed_at=confirmed_at,
        )
        if bound["outcome"] == "revised":
            return self._revise(
                request,
                transition,
                bound["edited_proposal"],
                attestation,
                base_revision,
            )
        if bound["outcome"] != "confirmed":
            return bound

        approval = bound["confirmation"].approval
        out_of_sequence = transitions.sequence_refusal(self._session, transition)
        if out_of_sequence is not None:
            return _refused(self._session, out_of_sequence)
        if transitions.find_target(self._session, transition["target_id"]) is None:
            return {
                "outcome": "refused",
                "code": "invariant_violation",
                "detail": f"no such target {transition['target_id']}",
                "phase": self._session.get("phase"),
                "events": [],
            }
        if base_revision != self._session.get("revision"):
            return {
                "outcome": "refused",
                "code": "approval_stale",
                "detail": "confirmation was bound to an older session revision",
                "phase": self._session.get("phase"),
                "events": [],
            }

        current_target = transitions.find_target(self._session, transition["target_id"])
        confirmed_candidate = candidate if candidate is not None else current_target
        if request["target_digest"] != transitions.content_digest(confirmed_candidate):
            return {
                "outcome": "refused",
                "code": "approval_stale",
                "detail": "confirmed proposal does not match the displayed target digest",
                "phase": self._session.get("phase"),
                "events": [],
            }

        if candidate is None and approval["disposition"] == "approved":
            refusal = transitions.binding_refusal(self._session, transition, approval)
            if refusal is not None:
                return _refused(self._session, refusal)

        self._confirmed[request_id] = bound["confirmation"]
        if candidate is not None:
            self._confirmed_candidates[request_id] = copy.deepcopy(candidate)
        self._pending.pop(request_id, None)
        return {
            "outcome": "confirmed",
            "code": None,
            "detail": "",
            "phase": self._session.get("phase"),
            "approval": approval,
            "candidate": copy.deepcopy(candidate),
            "events": [],
        }

    def confirmation(self, request_id: str):
        """Return in-process authority to orchestration, never to an MCP argument."""
        return self._confirmed.get(request_id)

    def confirmed_candidate(self, request_id: str) -> dict | None:
        """Return the confirmed edit for persistence to install with its disposition."""
        candidate = self._confirmed_candidates.get(request_id)
        return copy.deepcopy(candidate) if candidate is not None else None

    def _revise(
        self,
        request: dict,
        transition: dict,
        edited_proposal: str,
        attestation: dict,
        base_revision: int,
    ) -> dict:
        try:
            replacement = json.loads(edited_proposal)
        except json.JSONDecodeError as exc:
            return {
                "outcome": "pending",
                "code": "schema_invalid",
                "detail": f"edited proposal is not JSON: {exc.msg}",
                "events": [],
            }
        if not isinstance(replacement, dict) or replacement.get("id") != transition["target_id"]:
            return {
                "outcome": "pending",
                "code": "schema_invalid",
                "detail": "edited proposal must be an object retaining the displayed target id",
                "events": [],
            }

        revised = copy.deepcopy(self._session)
        revised["revision"] = request["session_revision"] + 1
        if "status" in replacement:
            replacement["status"] = "proposed"
        if "digest" in replacement:
            replacement["digest"] = transitions.content_digest(replacement)
        if not _replace_target(revised, transition["target_id"], replacement):
            return {
                "outcome": "pending",
                "code": "approval_stale",
                "detail": "target no longer exists",
                "events": [],
            }
        schema = "session.v2.schema.json" if revised.get("schema_version") == "2.0.0" else "session.v1.schema.json"
        violations = validate_against(revised, schema)
        if violations:
            return {
                "outcome": "pending",
                "code": "schema_invalid",
                "detail": "; ".join(violations),
                "events": [],
            }

        self._pending.pop(request["id"], None)
        fresh = build_request(
            request_id=f"{request['id']}.edit",
            session_id=request["session_id"],
            session_revision=revised["revision"],
            gate=request["gate"],
            target_id=request["target_id"],
            target_digest=transitions.content_digest(replacement),
            proposal=json.dumps(
                replacement,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            actor=attestation["operator"],
        )
        self._pending[fresh["id"]] = (
            fresh,
            dict(transition),
            replacement,
            base_revision,
        )
        return {
            "outcome": "revised",
            "code": "approval_required",
            "detail": "edited proposal is valid and requires a fresh native dialog",
            "confirmation_request": fresh,
            "events": [],
        }


def _replace_target(session: dict, target_id: str, replacement: dict) -> bool:
    for collection in transitions.TARGET_COLLECTIONS:
        for index, item in enumerate(session.get(collection, [])):
            if item.get("id") == target_id:
                session[collection][index] = replacement
                return True
    for index, item in enumerate(session.get("graph", {}).get("nodes", [])):
        if item.get("id") == target_id:
            session["graph"]["nodes"][index] = replacement
            return True
    return False


def _refused(session: dict, refusal) -> dict:
    return {
        "outcome": "refused",
        "code": refusal.code,
        "detail": refusal.detail,
        "phase": session.get("phase"),
        "events": [],
    }
