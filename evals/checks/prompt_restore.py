"""Prompt identity determines reasoning eligibility, never inspection integrity."""

import json
from pathlib import Path

from frameshift.bootstrap import installed_prompt_manifests, published_identities, restore_checkpoint
from frameshift.broker.confirmation import bind_confirmation_response, build_request
from frameshift.broker.port import request_digest
from frameshift.persistence import encode

ROOT = Path(__file__).resolve().parents[2]

APPROVAL_PROFILE = {
    "schema_version": "1.0.0",
    "id": "approval-profile-prompt-restore",
    "client_id": "eval-client",
    "client_version": "1.0.0",
    "config_digest": "sha256:" + "a" * 64,
    "validated": True,
}


def _confirm_changes(checkpoint: dict, selected_ids: list[str]) -> list:
    confirmations = []
    for change in checkpoint.get("prompt_version_changes", []):
        if change["id"] not in selected_ids:
            continue
        attestation = {
            "schema_version": "1.0.0",
            "profile_id": APPROVAL_PROFILE["id"],
            "client_id": APPROVAL_PROFILE["client_id"],
            "client_version": APPROVAL_PROFILE["client_version"],
            "config_digest": APPROVAL_PROFILE["config_digest"],
            "operator": change["actor"],
            "attested_at": change["created_at"],
        }
        request = build_request(
            request_id=f"confirm_{change['id']}",
            session_id=checkpoint["session_id"],
            session_revision=change["session_revision"],
            gate="decision_approval",
            target_id=change["id"],
            target_digest=request_digest(change),
            proposal=json.dumps(change, sort_keys=True, separators=(",", ":")),
            actor=change["actor"],
        )
        response = {
            "request_id": request["id"],
            "request_digest": request["request_digest"],
            "status": "submitted",
            "disposition": "approved",
            "edited_proposal": None,
        }
        outcome = bind_confirmation_response(
            request,
            response,
            attestation,
            APPROVAL_PROFILE,
            authorized_roles=frozenset({change["actor"]["role"]}),
            confirmed_at=change["created_at"],
        )
        confirmations.append(outcome["confirmation"])
    return confirmations


def prompt_restore(case: dict, load) -> list[str]:
    checkpoint = load(case["artifact"])
    synthetic_manifest = None
    synthetic_publication = None
    mutation = case.get("mutation")
    if mutation == "missing_prompt":
        checkpoint["contracts"]["prompts"]["problem_framing"]["id"] = "frameshift.missing.v2"
        checkpoint = encode(checkpoint)
    elif mutation == "unapproved_version_change":
        checkpoint["prompt_version_changes"] = []
        checkpoint = encode(checkpoint)
    elif mutation == "missing_prompt_pin":
        checkpoint["contracts"]["prompts"] = {}
        checkpoint = encode(checkpoint)
    elif mutation == "remove_earlier_execution":
        checkpoint["execution_summaries"] = checkpoint["execution_summaries"][-1:]
        checkpoint = encode(checkpoint)
    elif mutation == "sequential_upgrade":
        v2 = checkpoint["contracts"]["prompts"]["problem_framing"]
        v3 = {
            "id": "frameshift.problem-framing.v3",
            "version": "3.0.0",
            "digest": "sha256:" + "3" * 64,
        }
        checkpoint["contracts"]["prompts"]["problem_framing"] = v3
        checkpoint["execution_summaries"].append(
            {"execution_id": "exec_prompt_v3_001", "engine": "problem_framing", "prompt_contract": v3}
        )
        checkpoint["prompt_version_changes"].append(
            {
                "id": "prompt_change_002",
                "engine": "problem_framing",
                "from": v2,
                "to": v3,
                "actor": {"id": "user_owner", "kind": "human", "role": "decision_owner"},
                "session_revision": 2,
                "created_at": "2026-09-09T12:02:00Z",
            }
        )
        checkpoint = encode(checkpoint)
        synthetic_manifest = {
            **v3,
            "engine": "problem_framing",
            "body_digest": v3["digest"],
            "actual_body_digest": v3["digest"],
        }
        synthetic_publication = {
            "id": v3["id"], "version": v3["version"], "body_digest": v3["digest"]
        }
    elif mutation is not None:
        return [f"unknown prompt-restore mutation {mutation!r}"]

    manifests = installed_prompt_manifests(ROOT / "prompts")
    published = published_identities(ROOT / "prompts" / "releases")
    if synthetic_manifest is not None:
        manifests[synthetic_manifest["id"]] = synthetic_manifest
    if synthetic_publication is not None:
        published.append(synthetic_publication)
    plan = restore_checkpoint(
        checkpoint,
        {},
        installed_prompts=manifests,
        published_prompts=published,
        prompt_change_confirmations=_confirm_changes(
            checkpoint,
            case.get("confirmed_prompt_changes", []),
        ),
    )
    expected = case["expect"]
    errors: list[str] = []
    if plan["outcome"] != expected["outcome"]:
        errors.append(f"restore is {plan['outcome']}, expected {expected['outcome']}")
    if plan["reasoning_allowed"] != expected["reasoning_allowed"]:
        errors.append(
            f"reasoning_allowed is {plan['reasoning_allowed']}, expected {expected['reasoning_allowed']}: "
            f"{plan['contract_differences'] + plan['authorization_refusals']}"
        )
    fragment = expected.get("difference_contains")
    evidence = plan["contract_differences"] + plan["authorization_refusals"]
    if fragment and not any(fragment in item for item in evidence):
        errors.append(f"expected a restore refusal naming {fragment!r}, got {evidence}")
    return errors
