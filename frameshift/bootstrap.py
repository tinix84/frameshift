"""Assemble application operations and load their static contract resources."""

import argparse
import json
import sys
from datetime import datetime, timezone
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


def confirmation_server_main(argv: list[str] | None = None) -> int:
    """Assemble the narrow confirmation server from operator-owned resources."""
    from frameshift.mcp.confirmation_server import ConfirmationMcpServer, run_stdio
    from frameshift.orchestration.api import ConfirmationWorkflow
    from frameshift.persistence.canonical import digest

    parser = argparse.ArgumentParser(description="Serve one pending FrameShift confirmation over MCP")
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--transition", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--mcp-config-file", type=Path, required=True)
    parser.add_argument("--request-id", default="confirm_live_001")
    args = parser.parse_args(argv)

    paths = [
        args.profile.resolve(),
        args.attestation.resolve(),
        args.configuration.resolve(),
        args.mcp_config_file.resolve(),
    ]
    baseline_profile = _load_json(args.profile)
    protection_refusal = approval_configuration_refusal(
        baseline_profile,
        paths,
        Path.cwd().resolve(),
    )
    if protection_refusal:
        parser.error(protection_refusal)

    def load_profile() -> dict:
        profile = _load_json(args.profile)
        configuration = _load_json(args.configuration)
        required_flags = {"--restricted", "--strict-mcp-config", "--tools="}
        valid = (
            profile == baseline_profile
            and profile.get("config_digest") == digest(configuration)
            and configuration.get("client_id") == profile.get("client_id")
            and configuration.get("client_version") == profile.get("client_version")
            and required_flags <= set(configuration.get("launch_flags", []))
            and configuration.get("mcp_config_digest") == digest(_load_json(args.mcp_config_file))
        )
        return dict(profile, validated=bool(profile.get("validated") and valid))

    profile = load_profile()
    workflow = ConfirmationWorkflow(_load_json(args.session), profile)
    workflow.prepare(
        _load_json(args.transition),
        _load_json(args.attestation),
        request_id=args.request_id,
    )
    server = ConfirmationMcpServer(
        workflow,
        lambda: _load_json(args.attestation),
        load_profile,
        _utc_now,
    )
    run_stdio(server, sys.stdin, sys.stdout)
    return 0


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def approval_configuration_refusal(profile: dict, paths: list[Path], working_directory: Path) -> str | None:
    """A validated profile cannot be sourced from the agent-writable workspace."""
    if profile.get("validated") and any(_inside(path.resolve(), working_directory.resolve()) for path in paths):
        return "validated approval configuration must be outside the agent-writable working directory"
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "confirmation":
        raise SystemExit(confirmation_server_main(sys.argv[2:]))
    raise SystemExit("usage: python -m frameshift.bootstrap confirmation [options]")
