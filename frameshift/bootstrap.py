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
    prompt_change_confirmations=(),
    capability_profile: dict | None = None,
) -> dict:
    """Wire persistence evidence, prompt resources, broker authority and orchestration.

    `capability_profile` is the restoring adapter's manifest; differences from
    the recorded profile ride on the plan and a downgrade refuses it (#125).
    """
    from frameshift.orchestration.restore import plan_restore
    from frameshift.persistence import compatibility
    from frameshift.persistence.checkpoint import restore

    available = (
        installed_prompt_manifests(ROOT / "prompts")
        if installed_prompts is None
        else installed_prompts
    )
    base_plan = restore(checkpoint, artifact_bytes, journal, capability_profile=capability_profile)
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
        prompt_change_confirmations=prompt_change_confirmations,
    )


def confirmation_server_main(argv: list[str] | None = None) -> int:
    """Assemble the narrow confirmation server from operator-owned resources."""
    from frameshift.broker.confirmation import (
        approval_configuration_refusal,
        validated_approval_profile,
    )
    from frameshift.mcp.confirmation_server import ConfirmationMcpServer, run_stdio
    from frameshift.orchestration.api import ConfirmationWorkflow

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
        ROOT.resolve(),
    )
    if protection_refusal:
        parser.error(protection_refusal)

    def load_profile() -> dict:
        return validated_approval_profile(
            baseline_profile,
            _load_json(args.profile),
            _load_json(args.configuration),
            _load_json(args.mcp_config_file),
        )

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


GUI_CLIENT_ID = "frameshift-manual-gui"
GUI_CLIENT_VERSION = "0.1.0"
# ADR-0022: the claim the operator makes by launching the manual GUI. It is
# part of the pinned configuration, so rewording it is a change of profile.
MANUAL_ATTESTATION = "no agent or model runs under the operator's account while this server is open"


def gui_vocabulary() -> dict:
    """The enums the GUI offers, read from the published schemas, never copied."""
    from frameshift.validation import load_schema

    session = load_schema("session.v2.schema.json")["$defs"]
    graph = load_schema("graph.schema.json")["$defs"]
    common = load_schema("common.schema.json")["$defs"]
    return {
        "statement_roles": session["statement"]["properties"]["primary_role"]["enum"],
        "abstraction_levels": session["frame"]["properties"]["abstraction_level"]["enum"],
        "system_boundaries": session["frame"]["properties"]["system_boundary"]["enum"],
        "node_types": graph["node"]["properties"]["type"]["enum"],
        "edge_types": graph["edge"]["properties"]["type"]["enum"],
        "confidence": common["confidence"]["enum"],
    }


def manual_approval_configuration(
    store: Path, operator: dict, *, attested_at: str, bind: str = "127.0.0.1", public_hosts: tuple[str, ...] = ()
) -> tuple[dict, dict]:
    """The approval profile and attestation for the manual GUI (ADR-0022, ADR-0023).

    The operator attests by launching the server. What they attest is that no
    agent or model runs under their account while it is open: the process
    cannot check that, and an agent that could reach loopback could read the
    page and answer a confirmation. The digest pins the configuration, so a
    change to it is a change of profile and suspends approvals, as ADR-0014
    requires. Local and hosted runs are distinct profiles, so every approval
    records which trust boundary bound it.
    """
    from frameshift.persistence import canonical

    configuration = {
        "client_id": GUI_CLIENT_ID,
        "client_version": GUI_CLIENT_VERSION,
        "bind": bind,
        "public_hosts": sorted(public_hosts),
        "authentication": "basic" if public_hosts else "loopback",
        "model_connected": False,
        "operator_attests": MANUAL_ATTESTATION,
        "store": str(store.resolve()),
    }
    digest = canonical.digest(configuration)
    mode = "hosted" if public_hosts else "local"
    profile_id = f"approval-profile-{GUI_CLIENT_ID}-{mode}-{GUI_CLIENT_VERSION}"
    profile = {
        "schema_version": "1.0.0",
        "id": profile_id,
        "client_id": GUI_CLIENT_ID,
        "client_version": GUI_CLIENT_VERSION,
        "config_digest": digest,
        "validated": True,
    }
    attestation = {
        "schema_version": "1.0.0",
        "profile_id": profile_id,
        "client_id": GUI_CLIENT_ID,
        "client_version": GUI_CLIENT_VERSION,
        "config_digest": digest,
        "operator": dict(operator),
        "attested_at": attested_at,
    }
    return profile, attestation


def manual_coordinator(
    store: Path,
    operator: dict,
    *,
    clock=None,
    new_suffix=None,
    bind: str = "127.0.0.1",
    public_hosts: tuple[str, ...] = (),
):
    """Wire the JSON-lines store behind orchestration's port (#229, ADR-0015)."""
    import secrets

    from frameshift.orchestration.api import SessionCoordinator
    from frameshift.persistence.events import JsonlEventLog

    clock = clock or _utc_now
    profile, attestation = manual_approval_configuration(
        store, operator, attested_at=clock(), bind=bind, public_hosts=public_hosts
    )

    def suffix() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)

    return SessionCoordinator(
        JsonlEventLog(store),
        approval_profile=profile,
        attestation=attestation,
        clock=clock,
        new_suffix=new_suffix or suffix,
    )


MIN_PASSWORD_LENGTH = 16


def gui_main(argv: list[str] | None = None, environ: dict | None = None) -> int:
    """Serve the manual GUI. No model is connected in this mode.

    Locally it binds loopback. With `--hosted` it is configured from the
    environment for a container platform (ADR-0023) and refuses to
    start unless a password and a public host name are both set.
    """
    import os
    import secrets
    import webbrowser

    from frameshift.export.decision_record import render
    from frameshift.gui.server import ManualApp, serve

    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description="Run FrameShift with every proposal written by hand")
    parser.add_argument("--hosted", action="store_true",
                        help="listen on all interfaces, configured from FRAMESHIFT_* and platform variables")
    parser.add_argument("--store", type=Path, default=None,
                        help="directory for session event logs (default: ./.frameshift/sessions)")
    parser.add_argument("--operator", default=None, help="your actor id, as approvals will record it")
    parser.add_argument("--role", default=None,
                        choices=["decision_owner", "facilitator", "operator", "workspace_owner"])
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    operator_id = args.operator or env.get("FRAMESHIFT_OPERATOR") or "user_local"
    role = args.role or env.get("FRAMESHIFT_ROLE") or "decision_owner"
    operator = {"id": operator_id, "kind": "human", "role": role}

    if args.hosted:
        password = env.get("FRAMESHIFT_PASSWORD", "")
        public = env.get("FRAMESHIFT_PUBLIC_HOST") or env.get("RAILWAY_PUBLIC_DOMAIN") or ""
        if len(password) < MIN_PASSWORD_LENGTH:
            parser.error(f"--hosted requires FRAMESHIFT_PASSWORD of at least {MIN_PASSWORD_LENGTH} characters")
        if not public:
            parser.error("--hosted requires FRAMESHIFT_PUBLIC_HOST (or the platform's RAILWAY_PUBLIC_DOMAIN)")
        bind = "0.0.0.0"
        port = args.port or int(env.get("PORT", "8080"))
        public_hosts = (public, f"{public}:443")
        volume = env.get("RAILWAY_VOLUME_MOUNT_PATH")
        default_store = Path(volume) / "sessions" if volume else Path("/data/sessions")
    else:
        password, bind, public_hosts = None, "127.0.0.1", ()
        port = args.port or 8765
        default_store = Path(".frameshift") / "sessions"
    store = args.store or (Path(env["FRAMESHIFT_STORE"]) if env.get("FRAMESHIFT_STORE") else default_store)

    coordinator = manual_coordinator(store, operator, bind=bind, public_hosts=public_hosts)
    app = ManualApp(
        coordinator,
        token=secrets.token_urlsafe(24),
        vocabulary=gui_vocabulary(),
        record=render,
        password=password,
    )
    server = serve(app, port=port, host=bind, public_hosts=public_hosts)
    shown = f"https://{public_hosts[0]}/" if public_hosts else f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"FrameShift manual GUI on {shown}  (store: {store.resolve()}; operator: {operator_id})", flush=True)
    if not args.hosted:
        print(
            "Approvals here are yours only if " + MANUAL_ATTESTATION + ". "
            "An agent running as you can read this page and answer it (ADR-0022).",
            flush=True,
        )
    if not args.hosted and not args.no_browser:
        webbrowser.open(shown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "confirmation":
        raise SystemExit(confirmation_server_main(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "gui":
        raise SystemExit(gui_main(sys.argv[2:]))
    raise SystemExit("usage: python -m frameshift.bootstrap {confirmation|gui} [options]")
