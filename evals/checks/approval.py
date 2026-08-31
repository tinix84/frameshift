"""Approvals bind to a digest and a revision (ADR-0002).

A phase cannot advance without a typed human disposition bound to the content
being approved and the revision it was approved at. That is the property most
likely to erode quietly — a convenience path that accepts an approval with no
target, a retry that reuses a stale one, an adapter that advances a phase on its
own — so every way it can be wrong is a case that expects a refusal.

The reference guard here is deliberately implementation-agnostic: it asserts the
externally visible outcome, accepted or refused with which code, and reaches
into nothing. The orchestrator (#3) is measured against it, not described by it.
"""

from __future__ import annotations

from . import canonical, errors

# Stable codes from the application error vocabulary. Nothing new is invented,
# and `errors` is where the vocabulary lives so that stays true.
APPROVAL_REQUIRED = errors.APPROVAL_REQUIRED
APPROVAL_STALE = errors.APPROVAL_STALE
INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION

# The eight checkpoint gates named in CONTEXT.md, and who may pass each one.
# Roles are the first slice's reference policy; separation-of-duty rules are #16.
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

# Where a target may live in canonical state.
TARGET_COLLECTIONS = ("statements", "frames", "options", "criteria")


class Refusal(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


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
    return canonical.digest({key: value for key, value in target.items() if key != "digest"})


def attempt_transition(session: dict, transition: dict, approval: dict | None) -> dict:
    """Attempt one guarded transition. Returns the outcome; raises nothing."""
    gate = transition["gate"]
    try:
        if gate not in GATE_AUTHORITY:
            raise Refusal(INVARIANT_VIOLATION, f"unknown gate {gate}")

        target = find_target(session, transition["target_id"])
        if target is None:
            raise Refusal(INVARIANT_VIOLATION, f"no such target {transition['target_id']}")

        if approval is None:
            raise Refusal(APPROVAL_REQUIRED, f"gate {gate} has no approval")

        # An approval is a disposition, and only one disposition advances a phase.
        if approval.get("disposition") != "approved":
            raise Refusal(APPROVAL_REQUIRED, f"disposition is {approval.get('disposition')}")

        # A runtime cannot approve on a human's behalf.
        actor = approval.get("actor", {})
        if actor.get("kind") != "human":
            raise Refusal(INVARIANT_VIOLATION, f"actor kind {actor.get('kind')} cannot approve")
        if actor.get("role") not in GATE_AUTHORITY[gate]:
            raise Refusal(INVARIANT_VIOLATION, f"actor role {actor.get('role')} lacks authority for {gate}")

        if approval.get("target_id") != transition["target_id"]:
            raise Refusal(INVARIANT_VIOLATION, "approval targets something other than the transition")

        # Stale: the target digest or the revision no longer matches current state.
        if approval.get("session_revision") != session.get("revision"):
            raise Refusal(
                APPROVAL_STALE,
                f"session_revision {approval.get('session_revision')} trails session revision {session.get('revision')}",
            )
        if approval.get("target_digest") != content_digest(target):
            raise Refusal(APPROVAL_STALE, "target_digest does not match current content")
    except Refusal as refusal:
        return {"outcome": "refused", "code": refusal.code, "detail": refusal.detail, "phase": session.get("phase")}

    return {"outcome": "accepted", "code": None, "detail": "", "phase": transition.get("to_phase", session.get("phase"))}


def apply_edit(session: dict, edit: dict) -> dict:
    """Edit a target in place and bump the revision, as any real edit would."""
    target = find_target(session, edit["target_id"])
    target[edit["field"]] = edit["value"]
    if "digest" in target:
        target["digest"] = content_digest(target)
    session["revision"] = session.get("revision", 0) + 1
    return session


def bind_approval(session: dict, gate: str, target_id: str, actor: dict) -> dict:
    """A correctly bound approval, so the suite proves it is not refusing everything."""
    target = find_target(session, target_id)
    return {
        "id": f"appr_{gate}",
        "target_id": target_id,
        "target_digest": content_digest(target),
        "disposition": "approved",
        "actor": actor,
        "session_revision": session["revision"],
        "created_at": "2026-07-16T10:00:00Z",
    }


def _resolve_approval(session: dict, attempt: dict) -> dict | None:
    """A case either supplies an approval literally or asks for a bound one."""
    approval = attempt.get("approval")
    if approval is None:
        return None
    if approval.get("bind_to_current_content"):
        bound = bind_approval(session, attempt["gate"], attempt["target_id"], approval["actor"])
        for key in ("disposition", "session_revision", "target_id"):
            if key in approval:
                bound[key] = approval[key]
        return bound
    return approval


def approval_binding(case: dict, load) -> list[str]:
    """Run each declared attempt against a fresh copy of the starting state."""
    expect_coverage = case.get("expect", {}).get("covers_gates", False)
    errors: list[str] = []
    accepted_gates: set[str] = set()

    for attempt in case["attempts"]:
        session = load(case["session"])
        label = attempt["id"]

        # An edit happens before the attempt, exactly as a facilitator's would.
        if "edit" in attempt:
            apply_edit(session, attempt["edit"])

        approval = _resolve_approval(session, attempt)
        transition = {"gate": attempt["gate"], "target_id": attempt["target_id"], "to_phase": attempt.get("to_phase")}
        result = attempt_transition(session, transition, approval)
        expect = attempt["expect"]

        if result["outcome"] != expect["outcome"]:
            errors.append(f"{label}: outcome {result['outcome']} ({result['detail']}), case expects {expect['outcome']}")
            continue
        if result["outcome"] == "accepted":
            accepted_gates.add(attempt["gate"])
            continue
        if expect.get("violation") and result["code"] != expect["violation"]:
            errors.append(f"{label}: refused with {result['code']}, case expects {expect['violation']}")
        detail = expect.get("detail")
        if detail and detail not in result["detail"]:
            errors.append(f"{label}: detail {result['detail']!r} does not name {detail!r}")

    if expect_coverage:
        uncovered = sorted(set(GATE_AUTHORITY) - accepted_gates)
        if uncovered:
            errors.append(f"no accepted attempt for gates: {uncovered}")

    return errors
