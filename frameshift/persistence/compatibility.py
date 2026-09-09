"""Is this checkpoint compatible with what is installed here (#22 step 6)?

Step 6 of the restore algorithm is "check workspace/model/tool policy
compatibility". Two of those three need stores that do not exist: there is no
workspace policy object and no engine registry. The third is already recorded
and was going unchecked.

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

from frameshift.validation.prompts import PROMPTS, body_digest, parse_front_matter

# These are reports, not refusals, so they carry no error code. #126 set the
# precedent when comparing capability profiles: a difference is described, and
# only a refusal is coded. Inventing a code for something nobody refuses is how
# #24's vocabulary drifted the first time.


def installed_prompts() -> dict[str, dict]:
    """Committed prompt manifests, keyed by the id a checkpoint would pin."""
    found: dict[str, dict] = {}
    for path in sorted(PROMPTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        try:
            manifest = parse_front_matter(text)
        except ValueError:
            continue
        identifier = manifest.get("id")
        if isinstance(identifier, str):
            found[identifier] = {**manifest, "actual_body_digest": body_digest(text)}
    return found


def contract_differences(
    checkpoint: dict,
    installed: dict[str, dict] | None = None,
    published: list[dict] | None = None,
    confirmed_prompt_change_ids: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """What this checkpoint pins that this repository cannot honour."""
    available = installed_prompts() if installed is None else installed
    differences: list[str] = []

    for engine, pin in sorted(checkpoint.get("contracts", {}).get("prompts", {}).items()):
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
            if earlier:
                changes = checkpoint.get("prompt_version_changes", [])
                matching_changes = [
                    change
                    for change in changes
                    if isinstance(change, dict)
                    and change.get("engine") == engine
                    and change.get("from") in earlier
                    and change.get("to") == pin
                    and change.get("actor", {}).get("kind") == "human"
                ]
                approved = any(
                    change.get("id") in confirmed_prompt_change_ids
                    for change in matching_changes
                )
                if not approved:
                    if matching_changes:
                        differences.append(
                            f"prompt {prompt_id!r} version-change record lacks trusted confirmation"
                        )
                    else:
                        differences.append(
                            f"prompt {prompt_id!r} became active without a matching recorded version-change approval"
                        )

    return differences
