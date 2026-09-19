"""Is this checkpoint compatible with what is installed here (#22 steps 6 and 7)?

Step 6 of the restore algorithm is "check workspace/model/tool policy
compatibility". Two of those three need stores that do not exist: there is no
workspace policy object and no engine registry. The third is already recorded
and was going unchecked.

Step 7 is "report capability differences and pending approvals". A checkpoint
records the capability profile it was taken under and an adapter declares what
it offers; `capability_differences` compares the two. Most differences are
information — nothing auto-executes on restore, so a gain is not unsafe, but
an invisible gain is how a profile stops meaning anything. Two are refusals:
a weakened approval requirement is ADR-0002's gate crossed by changing
runtimes, and an escalated side effect is the same failure in another
dimension. Until #125 this comparison existed only as a harness check and
`restore` never read the recorded profile; the guard lives here now and the
check measures it.

A version-2 checkpoint pins exact prompt identities. Restore it into a
repository where a prompt has been deleted, renamed, rewritten, or is absent
from the published registry and its proposals cite reasoning nobody can
reproduce. The state remains valid and restorable for inspection; new
reasoning is blocked.

Rewriting is detectable because a prompt manifest carries a digest of its own
body (#144). Without that, a prompt could change under a fixed id and this check
would call it compatible.
"""

from __future__ import annotations

from frameshift.contracts import errors

# Prompt differences are reports, not refusals, so they carry no error code.
# #126 set the precedent when comparing capability profiles: a difference is
# described, and only a refusal is coded. Inventing a code for something nobody
# refuses is how #24's vocabulary drifted the first time.

# Mirrored from the enums in `schemas/capability-manifest.schema.json`, weakest
# gate first and least severe effect first. `frameshift/tests/test_persistence.py`
# asserts both still match the schema, so an enum gaining a value cannot
# silently order itself last here.
APPROVAL_STRENGTH = ("never", "policy", "each_call")
SIDE_EFFECT_SEVERITY = ("none", "reversible", "external", "irreversible")


def _by_id(profile: dict) -> dict[str, dict]:
    return {
        item["id"]: item
        for item in profile.get("capabilities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _rank(order: tuple[str, ...], value: object) -> int | None:
    return order.index(value) if value in order else None


def capability_differences(recorded: dict, offered: dict) -> dict[str, list[str]]:
    """What changed between the profile a checkpoint records and the one on offer.

    `reported` is attached to the plan; `refused` stops it. Each refusal carries
    its own code, because it is neither corruption nor a limit.
    """
    before, after = _by_id(recorded), _by_id(offered)
    reported: list[str] = []
    refused: list[str] = []
    downgrade = errors.CAPABILITY_DOWNGRADE_REFUSED

    if recorded.get("profile_id") != offered.get("profile_id"):
        reported.append(
            f"profile changed: recorded {recorded.get('profile_id')!r}, "
            f"adapter offers {offered.get('profile_id')!r}"
        )

    for name in sorted(set(before) - set(after)):
        reported.append(f"capability {name} is recorded but not offered by this adapter")
    for name in sorted(set(after) - set(before)):
        reported.append(f"capability {name} is offered by this adapter but not recorded")

    for name in sorted(set(before) & set(after)):
        was, now = before[name], after[name]
        if was.get("available") and not now.get("available"):
            reported.append(f"capability {name} was available and is not offered as available")

        was_gate, now_gate = _rank(APPROVAL_STRENGTH, was.get("approval")), _rank(
            APPROVAL_STRENGTH, now.get("approval")
        )
        if was_gate is not None and now_gate is not None and now_gate < was_gate:
            refused.append(
                f"{downgrade}: capability {name} approval weakened from "
                f"{was['approval']!r} to {now['approval']!r}"
            )

        was_effect, now_effect = _rank(SIDE_EFFECT_SEVERITY, was.get("side_effect")), _rank(
            SIDE_EFFECT_SEVERITY, now.get("side_effect")
        )
        if was_effect is not None and now_effect is not None and now_effect > was_effect:
            refused.append(
                f"{downgrade}: capability {name} side_effect escalated from "
                f"{was['side_effect']!r} to {now['side_effect']!r}"
            )

    return {"reported": reported, "refused": refused}


def _identity_key(identity: dict) -> tuple[object, object, object]:
    return (identity.get("id"), identity.get("version"), identity.get("digest"))


def _has_version_path(start: dict, target: dict, engine: str, changes: list[dict]) -> bool:
    """Whether recorded transitions connect a historical identity to the active one."""
    destination = _identity_key(target)
    edges: dict[tuple[object, object, object], set[tuple[object, object, object]]] = {}
    for change in changes:
        if not isinstance(change, dict) or change.get("engine") != engine:
            continue
        before, after = change.get("from"), change.get("to")
        if isinstance(before, dict) and isinstance(after, dict):
            edges.setdefault(_identity_key(before), set()).add(_identity_key(after))

    pending = [_identity_key(start)]
    visited: set[tuple[object, object, object]] = set()
    while pending:
        current = pending.pop()
        if current == destination:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(edges.get(current, set()) - visited)
    return False


def contract_differences(
    checkpoint: dict,
    installed: dict[str, dict],
    published: list[dict] | None = None,
) -> list[str]:
    """What this checkpoint pins that this repository cannot honour."""
    available = installed
    differences: list[str] = []

    contracts = checkpoint.get("contracts", {})
    pins = contracts.get("prompts", {})
    required_engines = set(contracts.get("engines", {}))
    required_engines.update(
        summary.get("engine")
        for summary in checkpoint.get("execution_summaries", [])
        if isinstance(summary, dict) and isinstance(summary.get("engine"), str)
    )
    for engine in sorted(required_engines - set(pins)):
        differences.append(
            f"engine {engine!r} has no prompt identity pinned, so new reasoning cannot reproduce its contract"
        )

    for engine, pin in sorted(pins.items()):
        prompt_id = pin.get("id") if isinstance(pin, dict) else pin
        manifest = available.get(prompt_id)
        if manifest is None:
            differences.append(
                f"the checkpoint pins prompt {prompt_id!r} for engine "
                f"{engine!r}, which is not installed here — its proposals cannot be reproduced"
            )
            continue

        declared = manifest.get("engine")
        if declared not in (engine, "shared"):
            differences.append(
                f"prompt {prompt_id!r} is pinned for engine {engine!r} "
                f"but declares engine {declared!r}"
            )

        recorded = manifest.get("body_digest")
        if recorded and recorded != manifest["actual_body_digest"]:
            differences.append(
                f"prompt {prompt_id!r} has been rewritten since its manifest "
                "was written, so what it says now is not what produced this checkpoint"
            )

        if isinstance(pin, dict):
            installed_identity = {
                "id": manifest.get("id"),
                "version": manifest.get("version"),
                "digest": manifest.get("actual_body_digest"),
            }
            if pin != installed_identity:
                differences.append(
                    f"prompt {prompt_id!r} does not match the exact identity pinned by the checkpoint"
                )
            matches = [
                item
                for item in (published or [])
                if item.get("id") == pin.get("id") and item.get("version") == pin.get("version")
            ]
            if len(matches) != 1 or matches[0].get("body_digest") != pin.get("digest"):
                differences.append(
                    f"prompt {prompt_id!r} has no matching independently published identity"
                )
        elif published is not None:
            differences.append(
                f"prompt {prompt_id!r} lacks the exact version and digest required for new reasoning"
            )

        if isinstance(pin, dict):
            earlier = [
                summary.get("prompt_contract")
                for summary in checkpoint.get("execution_summaries", [])
                if summary.get("engine") == engine
                and isinstance(summary.get("prompt_contract"), dict)
                and summary.get("prompt_contract") != pin
            ]
            changes = checkpoint.get("prompt_version_changes", [])
            for identity in earlier:
                if not _has_version_path(identity, pin, engine, changes):
                    differences.append(
                        f"prompt {prompt_id!r} became active without a matching recorded version-change approval"
                    )

    return differences
