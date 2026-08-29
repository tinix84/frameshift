"""Checkpoint digest stability, corruption detection, and restore (ADR-0004).

Two named checks. `checkpoint_digest` asserts a committed reference checkpoint
hashes to a recorded value, and that the value survives every difference that
carries no meaning. `checkpoint_integrity` mutates a copy at one of three levels
and asserts the mutation is refused before anything is restored.
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import canonical

INTEGRITY_VIOLATION = "checkpoint_integrity_failed"
ROOT = Path(__file__).resolve().parents[2]


# Differences that must not change a digest. Each returns a modified copy whose
# meaning is identical to the original's.
def _reverse_key_order(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_key_order(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_key_order(item) for item in value]
    return value


def _crlf_line_endings(value: object) -> object:
    if isinstance(value, dict):
        return {key: _crlf_line_endings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_crlf_line_endings(item) for item in value]
    if isinstance(value, str):
        return value.replace("\n", "\r\n")
    return value


def _reverse_set_order(value: object, field: str | None = None) -> object:
    if isinstance(value, dict):
        return {key: _reverse_set_order(item, key) for key, item in value.items()}
    if isinstance(value, list):
        items = [_reverse_set_order(item) for item in value]
        return list(reversed(items)) if field in canonical.SET_LIKE_FIELDS else items
    return value


def _replace_execution_metadata(value: dict) -> dict:
    checkpoint = copy.deepcopy(value)
    checkpoint["created_at"] = "2031-01-01T00:00:00Z"
    checkpoint["execution_summaries"] = [
        {
            "execution_id": "exec_reference_001",
            "latency_ms": 1,
            "token_counts": {"input": 1, "output": 1},
            "provider_request_id": "req_replaced",
        }
    ]
    return checkpoint


PERTURBATIONS = {
    "key_order": _reverse_key_order,
    "line_endings": _crlf_line_endings,
    "set_order": _reverse_set_order,
    "execution_metadata": _replace_execution_metadata,
}


def read_artifact(uri: str) -> bytes:
    """Referenced artifact bytes, with line endings normalized for a checkout."""
    return (ROOT / uri).read_bytes().replace(b"\r\n", b"\n")


def verify(checkpoint: dict, artifact_bytes: dict[str, bytes]) -> list[str]:
    """Return integrity violations. An empty list means the checkpoint is intact."""
    violations: list[str] = []
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


def plan_restore(checkpoint: dict, artifact_bytes: dict[str, bytes]) -> dict:
    """Restoring is not an action.

    Verification comes first, and a verified checkpoint yields a plan: what is
    pending, and which gates a human must still pass. Nothing is executed and
    nothing is committed, so restoring can never become a way to run a tool.
    """
    violations = verify(checkpoint, artifact_bytes)
    plan = {
        "outcome": "refused" if violations else "verified",
        "violations": violations,
        "executed_capabilities": [],
        "committed_proposal_ids": [],
        "pending_proposal_ids": [],
        "required_checkpoints": [],
    }
    if violations:
        return plan
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


def _set_path(container: object, path: list[str | int], value: object) -> None:
    for key in path[:-1]:
        container = container[key]
    container[path[-1]] = value


def checkpoint_digest(case: dict, load) -> list[str]:
    """A recorded digest, stable under every difference that carries no meaning."""
    checkpoint = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    computed_state = canonical.state_digest(checkpoint)
    computed_checkpoint = canonical.checkpoint_digest(checkpoint)
    for label, computed, recorded in (
        ("state_digest", computed_state, expect["state_digest"]),
        ("checkpoint_digest", computed_checkpoint, expect["checkpoint_digest"]),
    ):
        if computed != recorded:
            errors.append(f"{label} drifted: computed {computed}, case records {recorded}")
        if checkpoint.get(label) != recorded:
            errors.append(f"{label} in the checkpoint is {checkpoint.get(label)}, case records {recorded}")

    for reference in checkpoint.get("artifacts", []):
        payload = read_artifact(reference["uri"])
        if canonical.artifact_digest(payload) != reference["digest"]:
            errors.append(f"artifact {reference['id']} does not match its recorded digest")

    for name in expect.get("invariant_under", []):
        perturb = PERTURBATIONS.get(name)
        if perturb is None:
            errors.append(f"unknown perturbation: {name} (known: {sorted(PERTURBATIONS)})")
            continue
        perturbed = perturb(copy.deepcopy(checkpoint))
        if canonical.state_digest(perturbed) != computed_state:
            errors.append(f"{name} changed the state digest")
        if canonical.checkpoint_digest(perturbed) != computed_checkpoint:
            errors.append(f"{name} changed the checkpoint digest")

    return errors


def checkpoint_integrity(case: dict, load) -> list[str]:
    """Mutate a copy at one level, then assert the declared restore outcome."""
    checkpoint = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []
    override: dict[str, bytes] = {}

    mutation = case.get("mutate")
    if mutation is not None:
        level = mutation["level"]
        if level == "artifact":
            override[mutation["artifact_id"]] = mutation["bytes"].encode("utf-8")
        elif level in ("state", "envelope"):
            _set_path(checkpoint, mutation["path"], mutation["value"])
        else:
            return [f"unknown mutation level: {level} (known: artifact, envelope, state)"]

    payloads = {
        reference["id"]: override.get(reference["id"]) or read_artifact(reference["uri"])
        for reference in checkpoint.get("artifacts", [])
    }
    plan = plan_restore(checkpoint, payloads)

    if plan["outcome"] != expect["outcome"]:
        errors.append(f"restore outcome is {plan['outcome']}, case expects {expect['outcome']}")
    violation = expect.get("violation")
    if violation and not any(item.startswith(violation) for item in plan["violations"]):
        errors.append(f"expected {violation}, got {plan['violations'] or 'no violation'}")
    detail = expect.get("detail")
    if detail and not any(detail in item for item in plan["violations"]):
        errors.append(f"expected a violation naming {detail}, got {plan['violations']}")
    if plan["executed_capabilities"] or plan["committed_proposal_ids"]:
        errors.append("restore executed a capability or committed a proposal")
    for key in ("pending_proposal_ids", "required_checkpoints"):
        if key in expect and plan[key] != expect[key]:
            errors.append(f"{key} is {plan[key]}, case expects {expect[key]}")

    return errors
