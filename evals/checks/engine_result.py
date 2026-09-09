"""Engine-result envelope invariants (ADR-0006, ADR-0007)."""

from __future__ import annotations

from .schema import load_schema


# Ranking is explicit; the current frame contract keeps lateral boundaries
# separate. The evaluator checks equality with the ladder's closed value set.
LADDER_ORDER = ("component", "subsystem", "system", "product", "business")
LADDER_RANK = {level: rank for rank, level in enumerate(LADDER_ORDER)}


def _session_abstraction_levels() -> set[str]:
    schema = load_schema("session.schema.json")
    return set(schema["$defs"]["frame"]["properties"]["abstraction_level"]["enum"])


def _level_errors(level: object, location: str, ceiling: str) -> list[str]:
    if not isinstance(level, str) or level not in LADDER_RANK:
        return [f"non-ladder abstraction level {level!r} at {location} cannot be ranked"]
    if LADDER_RANK[level] > LADDER_RANK[ceiling]:
        return [f"{location} abstraction level {level!r} exceeds maximum {ceiling!r}"]
    return []


def engine_result_invariants(case: dict, load) -> list[str]:
    """Check a reference engine result against a case's declared expectations."""
    artifact = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    def string_list(name: str) -> set[str]:
        value = expect.get(name, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"{name} must be a list of strings")
            return set()
        return set(value)

    schema_levels = _session_abstraction_levels()
    missing_schema_levels = set(LADDER_ORDER) - schema_levels
    if missing_schema_levels:
        errors.append(f"ladder ordering is not a subset of session schema enum: {sorted(missing_schema_levels)}")
    extra_schema_levels = schema_levels - set(LADDER_ORDER)
    if extra_schema_levels:
        errors.append(f"session ladder enum contains unranked values: {sorted(extra_schema_levels)}")

    if artifact.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    if "frame_contract_version" in expect:
        if expect["frame_contract_version"] != "2.0.0":
            errors.append("unsupported frame contract version")
        frame_properties = load_schema("session.schema.json")["$defs"]["frame"]["properties"]
        for index, proposal in enumerate(artifact.get("proposals", [])):
            if proposal.get("kind") == "problem_frame":
                value = proposal.get("value", {})
                for axis in ("abstraction_level", "system_boundary"):
                    allowed = frame_properties[axis]["enum"]
                    if not isinstance(value, dict) or value.get(axis) not in allowed:
                        errors.append(f"proposal[{index}].value.{axis} must be one of {allowed}")

    proposal_kinds = {item.get("kind") for item in artifact.get("proposals", [])}
    missing_kinds = set(expect.get("required_proposal_kinds", [])) - proposal_kinds
    if missing_kinds:
        errors.append(f"missing proposal kinds: {sorted(missing_kinds)}")

    if "expected_ladder_levels" in expect:
        levels = expect["expected_ladder_levels"]
        if not isinstance(levels, list) or not levels or any(
            not isinstance(level, str) or level not in LADDER_RANK for level in levels
        ):
            errors.append("expected_ladder_levels must be a non-empty list of ranked levels")
        elif not any(
            proposal.get("kind") == "abstraction_ladder"
            and isinstance(proposal.get("value"), dict)
            and proposal["value"].get("levels") == levels
            for proposal in artifact.get("proposals", [])
        ):
            errors.append(f"no abstraction ladder matches expected levels: {levels}")

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

    forbidden_kinds = string_list("forbidden_proposal_kinds")
    found_forbidden = proposal_kinds & forbidden_kinds
    if found_forbidden:
        errors.append(f"forbidden proposal kinds were proposed: {sorted(found_forbidden)}")

    forbidden_checkpoints = string_list("forbid_checkpoints")
    found_checkpoints = checkpoints & forbidden_checkpoints
    if found_checkpoints:
        errors.append(f"forbidden checkpoints were required: {sorted(found_checkpoints)}")

    if "min_missing_information" in expect:
        minimum = expect["min_missing_information"]
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            errors.append("min_missing_information must be a non-negative integer")
        else:
            actual = len(artifact.get("missing_information", []))
            if actual < minimum:
                errors.append(f"{actual} missing information entries, expects at least {minimum}")

    if "max_abstraction_level" in expect:
        ceiling = expect["max_abstraction_level"]
        if not isinstance(ceiling, str) or ceiling not in LADDER_RANK:
            errors.append(f"non-ladder maximum abstraction level {ceiling!r} cannot be ranked")
        else:
            for index, proposal in enumerate(artifact.get("proposals", [])):
                value = proposal.get("value", {})
                if not isinstance(value, dict):
                    errors.append(f"proposal[{index}].value must be an object for abstraction comparison")
                    continue
                if proposal.get("kind") == "problem_frame":
                    errors.extend(_level_errors(value.get("abstraction_level"), f"proposal[{index}].value", ceiling))
                if proposal.get("kind") == "abstraction_ladder":
                    levels = value.get("levels")
                    if not isinstance(levels, list):
                        errors.append(f"proposal[{index}].value.levels must be a list for abstraction comparison")
                        continue
                    for level_index, level in enumerate(levels):
                        errors.extend(_level_errors(level, f"proposal[{index}].value.levels[{level_index}]", ceiling))

    return errors
