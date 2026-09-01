"""Is this checkpoint compatible with what is installed here (#22 step 6)?

Step 6 of the restore algorithm is "check workspace/model/tool policy
compatibility". Two of those three need stores that do not exist: there is no
workspace policy object and no engine registry. The third is already recorded
and was going unchecked.

A checkpoint pins the contracts it was produced under — `contracts.prompts`
names the prompt contract each engine used. Restore it into a repository where
that prompt has been deleted, renamed, or rewritten and the checkpoint's
proposals cite reasoning nobody can reproduce. The state is still valid and
still restorable, which is why this reports rather than refuses: what is lost is
the ability to re-run, not the ability to read.

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


def contract_differences(checkpoint: dict, installed: dict[str, dict] | None = None) -> list[str]:
    """What this checkpoint pins that this repository cannot honour."""
    available = installed_prompts() if installed is None else installed
    differences: list[str] = []

    for engine, prompt_id in sorted(checkpoint.get("contracts", {}).get("prompts", {}).items()):
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

    return differences
