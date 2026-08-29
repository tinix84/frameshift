"""Engine-result envelope invariants (ADR-0006, ADR-0007)."""

from __future__ import annotations


def engine_result_invariants(case: dict, load) -> list[str]:
    """Check a reference engine result against a case's declared expectations."""
    artifact = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    if artifact.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    proposal_kinds = {item.get("kind") for item in artifact.get("proposals", [])}
    missing_kinds = set(expect.get("required_proposal_kinds", [])) - proposal_kinds
    if missing_kinds:
        errors.append(f"missing proposal kinds: {sorted(missing_kinds)}")

    checkpoints = set(artifact.get("required_checkpoints", []))
    missing_checkpoints = set(expect.get("required_checkpoints", [])) - checkpoints
    if missing_checkpoints:
        errors.append(f"missing checkpoints: {sorted(missing_checkpoints)}")

    if len(artifact.get("rationale_summaries", [])) < expect.get("min_rationale_summaries", 0):
        errors.append("too few rationale summaries")
    if len(artifact.get("uncertainties", [])) < expect.get("min_uncertainties", 0):
        errors.append("too few uncertainties")

    if expect.get("forbid_approval_proposals", True):
        forbidden = [item for item in artifact.get("proposals", []) if item.get("kind") == "approval"]
        if forbidden:
            errors.append("engine result must not propose approval objects")

    return errors
