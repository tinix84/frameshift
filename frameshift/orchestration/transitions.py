"""Guarded transitions: sequence, then binding (#3, #1, ADR-0002).

`evals/checks/approval.py` is the reference guard — implementation-agnostic, it
asserts the externally visible outcome and reaches into nothing, so an
orchestrator is measured against it rather than described by it. This is the
orchestrator it measures.

Two guards apply and they stay apart. Sequence asks whether the transition may
happen from the phase the session is in; binding asks whether the approval is
good. Sequence runs first, because weighing an approval for a transition that
cannot happen is wasted work and a misleading error.

The refusal codes come from #24's published vocabulary. Nothing new is invented
here either.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import phases

APPROVAL_REQUIRED = "approval_required"
APPROVAL_STALE = "approval_stale"
INVARIANT_VIOLATION = "invariant_violation"

# The eight gates and who may pass each one. The first slice's reference policy;
# separation-of-duty rules are #16.
GATE_AUTHORITY = {
    "intake_correction": frozenset({"facilitator", "decision_owner"}),
    "frame_selection": frozenset({"decision_owner"}),
    "evidence_sufficiency": frozenset({"facilitator", "decision_owner"}),
    "option_set_acceptance": frozenset({"decision_owner"}),
    "criteria_confirmation": frozenset({"decision_owner"}),
    "decision_approval": frozenset({"decision_owner"}),
    "external_action": frozenset({"decision_owner", "operator"}),
    "knowledge_promotion": frozenset({"workspace_owner"}),
}

TARGET_COLLECTIONS = ("statements", "frames", "options", "criteria")


@dataclass(frozen=True)
class Refused(Exception):
    code: str
    detail: str


def find_target(session: dict, target_id: str) -> dict | None:
    for collection in TARGET_COLLECTIONS:
        for item in session.get(collection, []):
            if item.get("id") == target_id:
                return item
    for item in session.get("graph", {}).get("nodes", []):
        if item.get("id") == target_id:
            return item
    return None


def content_digest(target: dict) -> str:
    """A target's digest is over its content, never over its own digest field."""
    from frameshift.persistence import canonical

    return canonical.digest({key: value for key, value in target.items() if key != "digest"})


def sequence_refusal(session: dict, transition: dict) -> Refused | None:
    """May this transition happen from where the session is standing?"""
    refusals = phases.advance(session.get("phase"), transition["gate"], transition.get("to_phase"))
    if not refusals:
        return None
    detail = refusals[0].split(": ", 1)[1] if ": " in refusals[0] else refusals[0]
    return Refused(INVARIANT_VIOLATION, detail)


def binding_refusal(session: dict, transition: dict, approval: dict | None) -> Refused | None:
    """Is this approval a typed human disposition, bound to this content and revision?"""
    gate = transition["gate"]
    if approval is None:
        return Refused(APPROVAL_REQUIRED, f"gate {gate} has no approval")
    if approval.get("disposition") != "approved":
        return Refused(APPROVAL_REQUIRED, f"disposition is {approval.get('disposition')}")

    actor = approval.get("actor", {})
    if actor.get("kind") != "human":
        return Refused(INVARIANT_VIOLATION, f"actor kind {actor.get('kind')} cannot approve")
    if actor.get("role") not in GATE_AUTHORITY[gate]:
        return Refused(INVARIANT_VIOLATION, f"actor role {actor.get('role')} lacks authority for {gate}")
    if approval.get("target_id") != transition["target_id"]:
        return Refused(INVARIANT_VIOLATION, "approval targets something other than the transition")

    target = find_target(session, transition["target_id"])
    if approval.get("session_revision") != session.get("revision"):
        return Refused(
            APPROVAL_STALE,
            f"session_revision {approval.get('session_revision')} trails session revision "
            f"{session.get('revision')}",
        )
    if approval.get("target_digest") != content_digest(target):
        return Refused(APPROVAL_STALE, "target_digest does not match current content")
    return None


def attempt(session: dict, transition: dict, approval: dict | None) -> dict:
    """Attempt one guarded transition. Returns the outcome; raises nothing."""
    gate = transition["gate"]
    if gate not in GATE_AUTHORITY:
        return _refused(session, Refused(INVARIANT_VIOLATION, f"unknown gate {gate}"))

    out_of_sequence = sequence_refusal(session, transition)
    if out_of_sequence is not None:
        return _refused(session, out_of_sequence)

    if find_target(session, transition["target_id"]) is None:
        return _refused(session, Refused(INVARIANT_VIOLATION, f"no such target {transition['target_id']}"))

    unbound = binding_refusal(session, transition, approval)
    if unbound is not None:
        return _refused(session, unbound)

    return {
        "outcome": "accepted",
        "code": None,
        "detail": "",
        "phase": transition.get("to_phase", session.get("phase")),
    }


def _refused(session: dict, refusal: Refused) -> dict:
    return {
        "outcome": "refused",
        "code": refusal.code,
        "detail": refusal.detail,
        "phase": session.get("phase"),
    }
