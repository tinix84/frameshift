"""Encoding, verifying, and restoring a checkpoint (#2, ADR-0004).

Restore is the part with a safety property attached, and it is the reason this
module exists rather than a bare encoder. ADR-0004 says resuming is never an
action: verification comes first, and a verified checkpoint yields a *plan* —
what is pending and which gates a human must still pass — while nothing is
executed and nothing is committed.

Until now that was asserted against hard-coded empty lists (#102), so the guard
could not fail. Here it can. `restore` is handed a `RestoreJournal` and never
writes to it; the plan reports whatever the journal holds. A restore that
executed a capability or committed a proposal would have to record it, and the
guard reads the record rather than a literal — so a wrong implementation is
caught by the same check that passes a right one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import canonical

ROOT = Path(__file__).resolve().parents[2]

INTEGRITY_VIOLATION = "checkpoint_integrity_failed"
LIMIT_VIOLATION = "checkpoint_limits_exceeded"

# Step 1 of the restore algorithm: bound the checkpoint before anything walks it.
PARSE_LIMITS = {"max_bytes": 1_048_576, "max_depth": 64}


@dataclass
class RestoreJournal:
    """What a restore actually did, so "it did nothing" is measured, not asserted.

    A correct restore leaves both lists empty. It is passed in rather than
    returned so that a deliberately wrong implementation has somewhere to record
    its mistake, which is what gives #102's guard something real to read.
    """

    executed_capabilities: list[str] = field(default_factory=list)
    committed_proposal_ids: list[str] = field(default_factory=list)

    def record_execution(self, capability_id: str) -> None:
        self.executed_capabilities.append(capability_id)

    def record_commit(self, proposal_id: str) -> None:
        self.committed_proposal_ids.append(proposal_id)

    @property
    def acted(self) -> bool:
        return bool(self.executed_capabilities or self.committed_proposal_ids)


def encode(checkpoint: dict) -> dict:
    """Return the checkpoint with its two digests computed and set."""
    encoded = dict(checkpoint)
    encoded["state_digest"] = canonical.state_digest(encoded)
    encoded["checkpoint_digest"] = canonical.checkpoint_digest(encoded)
    return encoded


def depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((depth(item) for item in value), default=0)
    return 0


def limit_violations(checkpoint: object, limits: dict[str, int] = PARSE_LIMITS) -> list[str]:
    violations: list[str] = []
    measured = depth(checkpoint)
    if measured > limits["max_depth"]:
        violations.append(
            f"{LIMIT_VIOLATION}: nested {measured} deep, max_depth is {limits['max_depth']}"
        )
    size = len(canonical.canonical_bytes(checkpoint))
    if size > limits["max_bytes"]:
        violations.append(f"{LIMIT_VIOLATION}: {size} bytes, max_bytes is {limits['max_bytes']}")
    return violations


def verify(checkpoint: dict, artifact_bytes: dict[str, bytes]) -> list[str]:
    """Integrity violations. An empty list means the checkpoint is intact."""
    violations = limit_violations(checkpoint)
    if violations:
        return violations
    if canonical.state_digest(checkpoint) != checkpoint.get("state_digest"):
        violations.append(f"{INTEGRITY_VIOLATION}: state_digest")
    if canonical.checkpoint_digest(checkpoint) != checkpoint.get("checkpoint_digest"):
        violations.append(f"{INTEGRITY_VIOLATION}: checkpoint_digest")
    for reference in checkpoint.get("artifacts", []):
        payload = artifact_bytes.get(reference["id"])
        if payload is None:
            violations.append(f"{INTEGRITY_VIOLATION}: artifact {reference['id']} is missing")
        elif canonical.artifact_digest(payload) != reference["digest"]:
            violations.append(f"{INTEGRITY_VIOLATION}: artifact {reference['id']}")
    return violations


def restore(
    checkpoint: dict,
    artifact_bytes: dict[str, bytes],
    journal: RestoreJournal | None = None,
) -> dict:
    """Verify, then plan. Never execute and never commit.

    The plan names what is pending and which gates remain. Both action lists come
    from the journal, so they are a record of what happened rather than a claim
    about what should have.
    """
    journal = journal if journal is not None else RestoreJournal()
    violations = verify(checkpoint, artifact_bytes)

    plan = {
        "outcome": "refused" if violations else "verified",
        "violations": violations,
        "executed_capabilities": list(journal.executed_capabilities),
        "committed_proposal_ids": list(journal.committed_proposal_ids),
        "pending_proposal_ids": [],
        "required_checkpoints": [],
    }
    if violations:
        return plan

    # Reading a pending proposal is not committing it: the ids are listed so a
    # human can see what awaits a gate, and nothing here advances a phase.
    plan["pending_proposal_ids"] = [
        proposal["id"]
        for result in checkpoint.get("pending_proposals", [])
        for proposal in result.get("proposals", [])
    ]
    plan["required_checkpoints"] = sorted(
        {
            gate
            for result in checkpoint.get("pending_proposals", [])
            for gate in result.get("required_checkpoints", [])
        }
    )
    return plan
