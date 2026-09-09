"""Executable linked-session frame-axis migration contract (#86)."""

from __future__ import annotations

import copy

from . import checkpoint as reference_checkpoint


def frame_migration(case: dict, load) -> list[str]:
    from frameshift.persistence import checkpoint, migration
    from frameshift.validation import validate_against

    errors: list[str] = []
    source = load(case["source"])
    before = copy.deepcopy(source)
    payloads = {
        reference["id"]: reference_checkpoint.read_artifact(reference["uri"])
        for reference in source.get("artifacts", [])
    }
    result = migration.migrate_frame_axes(
        source,
        payloads,
        checkpoint_id=case["target"]["checkpoint_id"],
        session_id=case["target"]["session_id"],
        prompt_identities=case["target"]["prompt_identities"],
        created_at=case["target"]["created_at"],
    )
    if source != before:
        errors.append("migration mutated the source checkpoint")
    if result["outcome"] != "migrated":
        errors.append(f"migration outcome was {result['outcome']}: {result['detail']}")
        return errors

    migrated = result["checkpoint"]
    if validate_against(migrated, "checkpoint.v2.schema.json"):
        errors.append("migrated checkpoint does not satisfy the v2 schema")
    integrity = reference_checkpoint.verify(migrated, payloads)
    if integrity:
        errors.append(f"migrated checkpoint failed independent integrity verification: {integrity}")
    for field, expected in case["expect"]["source_checkpoint"].items():
        if migrated.get("source_checkpoint", {}).get(field) != expected:
            errors.append(f"source checkpoint {field} was not preserved")
    if migrated["event_cursor"] != 0 or migrated["session_revision"] != 0:
        errors.append("linked migration inherited the source event or revision sequence")
    state = migrated["state"]
    if state["approvals"] or state.get("active_frame_id") is not None:
        errors.append("linked migration inherited approval authority")
    frame = state["frames"][0]
    for field, expected in case["expect"]["frame"].items():
        if frame.get(field) != expected:
            errors.append(f"migrated frame {field} is {frame.get(field)!r}, expected {expected!r}")
    if frame["digest"] == source["state"]["frames"][0]["digest"]:
        errors.append("changed frame retained its legacy digest")

    ambiguous = copy.deepcopy(source)
    ambiguous["state"]["frames"][0]["abstraction_level"] = case["ambiguous_value"]
    ambiguous = checkpoint.encode(ambiguous)
    pending = migration.migrate_frame_axes(
        ambiguous,
        payloads,
        checkpoint_id="ckpt_ambiguous_v2_eval",
        session_id="sess_ambiguous_v2_eval",
        prompt_identities=case["target"]["prompt_identities"],
        created_at=case["target"]["created_at"],
    )
    if pending.get("outcome") != "pending" or pending.get("code") != "approval_required":
        errors.append(f"ambiguous frame conversion did not require human review: {pending}")
    if pending.get("checkpoint") is not None:
        errors.append("ambiguous frame conversion produced a checkpoint")
    return errors
