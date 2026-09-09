"""Provider-neutral application operation for trusted confirmation (#205)."""

from __future__ import annotations

import copy
import json

from frameshift.broker.confirmation import bind_native_response, build_request
from frameshift.validation import validate_against

from . import transitions


class ConfirmationWorkflow:
    """Hold pending confirmations for an independently executable vertical slice."""

    def __init__(self, session: dict, approval_profile: dict) -> None:
        self._session = copy.deepcopy(session)
        self._profile = copy.deepcopy(approval_profile)
        self._pending: dict[str, tuple[dict, dict]] = {}

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
        self._pending[request_id] = (request, dict(transition))
        return copy.deepcopy(request)

    def pending(self, request_id: str) -> dict | None:
        entry = self._pending.get(request_id)
        return copy.deepcopy(entry[0]) if entry else None

    def complete(
        self,
        request_id: str,
        response: dict,
        attestation: dict,
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
        request, transition = entry
        gate = transition["gate"]
        roles = transitions.GATE_AUTHORITY.get(gate, frozenset())
        bound = bind_native_response(
            request,
            response,
            attestation,
            self._profile,
            authorized_roles=roles,
            confirmed_at=confirmed_at,
        )
        if bound["outcome"] == "revised":
            return self._revise(request, transition, bound["edited_proposal"], attestation)
        if bound["outcome"] != "confirmed":
            return bound

        result = transitions.attempt(self._session, transition, bound["confirmation"])
        if result["outcome"] == "accepted":
            self._pending.pop(request_id, None)
        return result

    def _revise(self, request: dict, transition: dict, edited_proposal: str, attestation: dict) -> dict:
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
        if "digest" in replacement:
            replacement["digest"] = transitions.content_digest(replacement)
        if not _replace_target(revised, transition["target_id"], replacement):
            return {
                "outcome": "pending",
                "code": "approval_stale",
                "detail": "target no longer exists",
                "events": [],
            }
        revised["revision"] += 1
        schema = "session.v2.schema.json" if revised.get("schema_version") == "2.0.0" else "session.v1.schema.json"
        violations = validate_against(revised, schema)
        if violations:
            return {
                "outcome": "pending",
                "code": "schema_invalid",
                "detail": "; ".join(violations),
                "events": [],
            }

        self._session = revised
        self._pending.pop(request["id"], None)
        fresh = self.prepare(
            transition,
            attestation,
            request_id=f"{request['id']}.r{revised['revision']}",
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
