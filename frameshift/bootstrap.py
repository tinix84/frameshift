"""Assemble application operations and load their static contract resources."""

import json
from pathlib import Path

from frameshift.validation.prompts import body_digest, parse_front_matter

ROOT = Path(__file__).resolve().parents[1]


def installed_prompt_manifests(prompts: Path) -> dict[str, dict]:
    """Committed prompt manifests, keyed by the identity a request pins."""
    found: dict[str, dict] = {}
    for path in sorted(prompts.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        try:
            manifest = parse_front_matter(text)
        except ValueError:
            continue
        identifier = manifest.get("id")
        if isinstance(identifier, str):
            found[identifier] = {**manifest, "actual_body_digest": body_digest(text)}
    return found


def published_identities(releases: Path) -> list[dict]:
    """Read reviewed release records, not installed prompt self-declarations."""
    entries: list[dict] = []
    for path in sorted(releases.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        entries.extend(record["prompts"])
    return entries


def restore_checkpoint(
    checkpoint: dict,
    artifact_bytes: dict[str, bytes],
    journal=None,
    *,
    installed_prompts: dict[str, dict] | None = None,
    published_prompts: list[dict] | None = None,
    confirmed_prompt_change_ids: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """Wire persistence evidence, prompt resources, broker authority and orchestration."""
    from frameshift.orchestration.restore import plan_restore
    from frameshift.persistence import compatibility
    from frameshift.persistence.checkpoint import restore

    available = (
        installed_prompt_manifests(ROOT / "prompts")
        if installed_prompts is None
        else installed_prompts
    )
    base_plan = restore(checkpoint, artifact_bytes, journal)
    differences = (
        compatibility.contract_differences(checkpoint, available, published_prompts)
        if base_plan["outcome"] == "verified"
        else []
    )
    return plan_restore(
        checkpoint,
        base_plan,
        differences,
        published_registry_supplied=published_prompts is not None,
        confirmed_prompt_change_ids=confirmed_prompt_change_ids,
    )
