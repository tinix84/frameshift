"""Explicit, source-preserving checkpoint migrations (#86, ADR-0019)."""

from __future__ import annotations

import copy

from frameshift.validation import validate_against

from . import canonical, checkpoint

SCHEMA_INVALID = "schema_invalid"
INVARIANT_VIOLATION = "invariant_violation"
APPROVAL_REQUIRED = "approval_required"

_AUTOMATIC_AXES = {
    "component": ("component", "component"),
    "subsystem": ("subsystem", "subsystem"),
    "product": ("product", "product"),
    "business": ("business", "business_model"),
}


def migrate_frame_axes(
    source: dict,
    artifact_bytes: dict[str, bytes],
    *,
    checkpoint_id: str,
    session_id: str,
    prompt_identities: dict[str, dict],
    created_at: str,
) -> dict:
    """Create a linked v2 checkpoint, or report the review still required.

    The source is input only. A migration begins a new session revision and
    event sequence, carries no approval records, and returns changed frames as
    proposals. Lateral legacy values cannot supply a missing ladder value, so
    they remain pending human review instead of being guessed.
    """
    if source.get("schema_version") != "1.0.0":
        return _refused(
            SCHEMA_INVALID,
            f"unsupported source checkpoint schema version {source.get('schema_version')!r}",
        )

    invalid_source = validate_against(source, "checkpoint.schema.json")
    if invalid_source:
        return _refused(SCHEMA_INVALID, "; ".join(invalid_source))
    integrity = checkpoint.verify(source, artifact_bytes)
    if integrity:
        return _refused(checkpoint.INTEGRITY_VIOLATION, "; ".join(integrity))

    if checkpoint_id == source["id"] or session_id == source["session_id"]:
        return _refused(
            INVARIANT_VIOLATION,
            "linked migration requires new checkpoint and session identifiers",
        )

    engines = source["contracts"]["engines"]
    if set(prompt_identities) != set(engines):
        return _refused(
            SCHEMA_INVALID,
            "target prompt identities must name exactly the migrated session's engines",
        )

    reviews = []
    for frame in source["state"]["frames"]:
        legacy = frame["abstraction_level"]
        if legacy not in _AUTOMATIC_AXES:
            reviews.append(
                {
                    "frame_id": frame["id"],
                    "legacy_abstraction_level": legacy,
                    "required_fields": ["abstraction_level", "system_boundary"],
                }
            )
    if reviews:
        return {
            "outcome": "pending",
            "code": APPROVAL_REQUIRED,
            "detail": "one or more legacy frame axes require human review",
            "review_kind": "frame_axis_mapping",
            "reviews": reviews,
            "checkpoint": None,
        }

    state = copy.deepcopy(source["state"])
    state.update(
        {
            "schema_version": "2.0.0",
            "id": session_id,
            "phase": "framing",
            "revision": 0,
            "active_frame_id": None,
            "approvals": [],
        }
    )
    for frame in state["frames"]:
        abstraction_level, system_boundary = _AUTOMATIC_AXES[frame["abstraction_level"]]
        frame["abstraction_level"] = abstraction_level
        frame["system_boundary"] = system_boundary
        frame["status"] = "proposed"
        frame["digest"] = canonical.digest(
            {key: value for key, value in frame.items() if key != "digest"}
        )

    migrated = {
        "schema_version": "2.0.0",
        "id": checkpoint_id,
        "session_id": session_id,
        "session_revision": 0,
        "phase": "framing",
        "state": state,
        "pending_proposals": [],
        "event_cursor": 0,
        "prior_checkpoint_digest": None,
        "source_checkpoint": {
            "id": source["id"],
            "digest": source["checkpoint_digest"],
            "schema_version": source["schema_version"],
        },
        "contracts": {
            "engines": copy.deepcopy(engines),
            "prompts": copy.deepcopy(prompt_identities),
        },
        "capability_profile": copy.deepcopy(source["capability_profile"]),
        "artifacts": copy.deepcopy(source["artifacts"]),
        "execution_summaries": [],
        "prompt_version_changes": [],
        "created_at": created_at,
    }
    migrated = checkpoint.encode(migrated)
    invalid_migrated = validate_against(migrated, "checkpoint.v2.schema.json")
    if invalid_migrated:
        return _refused(SCHEMA_INVALID, "; ".join(invalid_migrated))
    return {
        "outcome": "migrated",
        "code": None,
        "detail": "",
        "checkpoint": migrated,
    }


def _refused(code: str, detail: str) -> dict:
    return {"outcome": "refused", "code": code, "detail": detail, "checkpoint": None}
