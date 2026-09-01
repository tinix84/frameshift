"""A proposal formed against old state is stale (#24, ADR-0002).

#24 states it in one line under Idempotency and concurrency:

    Long executions pin an input revision; their results become stale
    proposals if the session advances.

Nothing enforced it. The adapter port checks a result's `input_revision`
against the *request* that asked for it, which catches an adapter answering the
wrong question — but says nothing about the session the answer would be applied
to. An engine that took ninety seconds while a human edited a statement returns
proposals about a session that no longer exists, and every one of them
validates.

This is ADR-0002's staleness rule in the other direction. That rule stops a
human approving A while B is committed; this stops an engine proposing against A
while the session has moved to B. Both are the same failure — acting on a state
nobody is looking at any more — and the second had no guard.

Stale is not invalid. #24 says such results *become stale proposals*, not
discarded ones: a human may still read them, and re-running the engine is a
choice rather than an obligation. What must not happen is a stale proposal being
committed as though it were current, so the refusal is on admitting it, not on
holding it.
"""

from __future__ import annotations

# Both codes are published in #24. They live beside the other application
# codes in `transitions`, so there is one place to read the vocabulary from.
from frameshift.orchestration.transitions import INVARIANT_VIOLATION, REVISION_CONFLICT


def staleness(result: dict, session: dict) -> str:
    """`current`, `stale`, or `impossible` — where the result sits against the session."""
    pinned = result.get("input_revision")
    current = session.get("revision")
    if not isinstance(pinned, int) or not isinstance(current, int):
        return "impossible"
    if pinned > current:
        return "impossible"
    return "current" if pinned == current else "stale"


def admission_refusals(result: dict, session: dict) -> list[str]:
    """Why this result may not be committed to this session as it stands."""
    pinned = result.get("input_revision")
    current = session.get("revision")
    state = staleness(result, session)

    if state == "impossible":
        return [
            f"{INVARIANT_VIOLATION}: result pins revision {pinned!r} against a session at "
            f"{current!r} — it claims to have seen state that does not exist"
        ]
    if state == "stale":
        behind = current - pinned
        return [
            f"{REVISION_CONFLICT}: result was formed against revision {pinned} and the session "
            f"is at {current}, {behind} revision{'s' if behind != 1 else ''} later — "
            "re-run the engine or have a human re-read the proposals"
        ]
    return []


def admit(result: dict, session: dict) -> dict:
    """Decide whether a result's proposals may be committed to this session.

    Returns the disposition and the proposals it covers. A stale result keeps
    its proposals — they are readable, just not committable — because throwing
    away ninety seconds of work a human might still want is its own failure.
    """
    refusals = admission_refusals(result, session)
    return {
        "outcome": "admitted" if not refusals else "held",
        "staleness": staleness(result, session),
        "refusals": refusals,
        "proposal_ids": [
            proposal["id"]
            for proposal in result.get("proposals", [])
            if isinstance(proposal, dict) and isinstance(proposal.get("id"), str)
        ],
    }
