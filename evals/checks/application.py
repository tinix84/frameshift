"""The application encoder is measured against the reference (#2, ADR-0004).

`evals/checks/canonical.py` is the reference the harness owns; it exists so
digest stability was verifiable before any application did. `frameshift`
supplies the real encoder. Two independent implementations agreeing on a digest
is the evidence #2 asks for, and it is only evidence while they stay
independent — so this compares them rather than importing one into the other.

Byte equality is the assertion, not digest equality alone. Two encoders can
agree on a hash by coincidence of input; agreeing on the exact canonical bytes
means they agree on every rule that produced them.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import canonical as reference_canonical
from . import schema as reference

FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


def application_encoder(case: dict, load) -> list[str]:
    """Compare the application encoder to the reference and to what is recorded."""
    from frameshift.persistence import canonical as application

    checkpoint = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    if application.set_like_fields() != reference_canonical.SET_LIKE_FIELDS:
        errors.append(
            "the two encoders disagree about which arrays are sets: "
            f"application {sorted(application.set_like_fields())}, "
            f"reference {sorted(reference_canonical.SET_LIKE_FIELDS)}"
        )

    for label, produced, recorded in (
        ("state_digest", application.state_digest(checkpoint), checkpoint["state_digest"]),
        (
            "checkpoint_digest",
            application.checkpoint_digest(checkpoint),
            checkpoint["checkpoint_digest"],
        ),
    ):
        if produced != recorded:
            errors.append(
                f"the application encoder produced {label} {produced}, "
                f"the checkpoint records {recorded}"
            )

    app_bytes = application.canonical_bytes(checkpoint["state"])
    reference_bytes = reference_canonical.encode(
        reference_canonical._order_sets(reference_canonical.canonicalize(checkpoint["state"]))
    ).encode("utf-8")
    if app_bytes != reference_bytes:
        errors.append(
            "the two encoders produced different canonical bytes for the same state"
        )

    if expect.get("byte_identical") and errors:
        return errors
    for name in expect.get("invariant_under", []):
        perturb = _PERTURBATIONS.get(name)
        if perturb is None:
            errors.append(f"unknown perturbation: {name} (known: {sorted(_PERTURBATIONS)})")
            continue
        perturbed = perturb(checkpoint)
        if application.state_digest(perturbed) != checkpoint["state_digest"]:
            errors.append(f"{name} changed the application's state digest")

    return errors


def _respell(value: object) -> object:
    if isinstance(value, dict):
        return {key: _respell(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_respell(item) for item in value]
    if isinstance(value, str) and reference_canonical.TIMESTAMP.match(value):
        return value.lower()
    return value


def _reverse_keys(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


_PERTURBATIONS = {"key_order": _reverse_keys, "timestamp_spelling": _respell}


def application_validator(case: dict, load) -> list[str]:
    """The application validator agrees with the reference, fault for fault.

    Agreeing that a valid artifact is valid proves little. What matters is that
    two independently written validators produce the *same violations* for the
    same fault — same paths, same messages — because that is what lets the
    application refuse at runtime exactly what the corpus refuses at review.
    """
    import copy

    from frameshift.validation import invariants as application_invariants
    from frameshift.validation import schema as application_schema

    from . import session as reference_invariants

    artifact = load(case["artifact"])
    for key in case.get("at", []):
        artifact = artifact[key]
    schema_name = case["schema"]
    expect = case["expect"]
    errors: list[str] = []

    def both(value: object) -> tuple[list[str], list[str]]:
        mine = application_schema.validate_against(value, schema_name)
        theirs = reference.validate(
            value, reference.load_schema(schema_name), current=schema_name
        )
        if case.get("invariants"):
            mine = mine + application_invariants.reference_violations(value)
            theirs = theirs + reference_invariants.reference_violations(value)
        return mine, theirs

    mine, theirs = both(artifact)
    if mine != theirs:
        errors.append(f"the validators disagree on the clean artifact: {mine} vs {theirs}")
    if mine:
        errors.append(f"the committed artifact is not valid: {mine}")

    detected = 0
    for index, fault in enumerate(case.get("faults", [])):
        planted = copy.deepcopy(artifact)
        container = planted
        for key in fault["path"][:-1]:
            container = container[key]
        container[fault["path"][-1]] = fault["value"]

        mine, theirs = both(planted)
        if mine != theirs:
            errors.append(
                f"fault {index} at {fault['path']}: application says {mine}, reference says {theirs}"
            )
        if mine:
            detected += 1
        else:
            errors.append(f"fault {index} at {fault['path']} produced no violation at all")

    minimum = expect.get("min_faults_detected", 1)
    if detected < minimum:
        errors.append(f"{detected} faults detected, case expects at least {minimum}")
    return errors


def application_orchestrator(case: dict, load) -> list[str]:
    """Every approval-corpus attempt, run through the real orchestrator.

    #3 asks for the eight-gate corpus passing against a real orchestrator rather
    than against the reference guard. The reference stays what it always was —
    implementation-agnostic, asserting only the externally visible outcome — and
    this asserts the application reaches the same outcome, code for code, on
    every attempt the corpus declares.
    """
    from frameshift.orchestration import attempt as application_attempt

    from . import approval as reference_guard

    expect = case["expect"]
    errors: list[str] = []
    attempts = 0
    gates_accepted: set[str] = set()

    for path in sorted(FIXTURES.glob("approval-*.case.json")):
        with path.open("r", encoding="utf-8") as handle:
            corpus_case = json.load(handle)
        if corpus_case.get("check") != "approval_binding":
            continue
        for item in corpus_case.get("attempts", []):
            session = load(corpus_case["session"])
            if "from_phase" in item:
                session["phase"] = item["from_phase"]
            if "edit" in item:
                reference_guard.apply_edit(session, item["edit"])

            approval = reference_guard._resolve_approval(session, item)
            transition = {
                "gate": item["gate"],
                "target_id": item["target_id"],
                "to_phase": item.get("to_phase"),
            }
            theirs = reference_guard.attempt_transition(session, transition, approval)
            mine = application_attempt(session, transition, approval)
            attempts += 1

            label = f"{corpus_case['id']}/{item['id']}"
            for field in ("outcome", "code", "detail"):
                if mine[field] != theirs[field]:
                    errors.append(
                        f"{label}: application {field} {mine[field]!r}, reference {theirs[field]!r}"
                    )
            if mine["outcome"] == "accepted":
                gates_accepted.add(item["gate"])

    minimum = expect.get("min_attempts", 1)
    if attempts < minimum:
        errors.append(f"{attempts} attempts run, case expects at least {minimum}")
    if expect.get("covers_gates"):
        uncovered = sorted(set(reference_guard.GATE_AUTHORITY) - gates_accepted)
        if uncovered:
            errors.append(f"the orchestrator accepted no attempt for gates: {uncovered}")
    return errors


def prompt_manifests(case: dict, load) -> list[str]:
    """Every prompt declares a manifest, and its references resolve (#20)."""
    from frameshift.validation import prompt_manifest_violations, parse_front_matter

    expect = case["expect"]
    errors: list[str] = []

    root = Path(__file__).resolve().parents[2]
    prompts = sorted((root / "prompts").glob("*.md"))
    minimum = expect.get("min_prompts", 1)
    if len(prompts) < minimum:
        errors.append(f"{len(prompts)} prompts found, case expects at least {minimum}")

    violations = prompt_manifest_violations()
    outcome = "invalid" if violations else "valid"
    if outcome != expect["outcome"]:
        errors.append(f"prompt manifests are {outcome}, case expects {expect['outcome']}: {violations}")

    # The repair corpus pins a prompt by id and version; the manifest is where
    # those come from, so the two must agree or the pin is checking a fiction.
    pinned = {}
    for path in sorted((root / "evals" / "fixtures").glob("*.case.json")):
        with path.open("r", encoding="utf-8") as handle:
            other = json.load(handle)
        pin = other.get("prompt")
        if pin:
            pinned[pin["path"]] = (pin["id"], pin["version"])
    for relative, (identifier, version) in sorted(pinned.items()):
        manifest = parse_front_matter((root / relative).read_text(encoding="utf-8"))
        if (manifest.get("id"), manifest.get("version")) != (identifier, version):
            errors.append(
                f"{relative}: corpus pins {identifier} {version}, manifest declares "
                f"{manifest.get('id')} {manifest.get('version')}"
            )
    if expect.get("pins_checked") and not pinned:
        errors.append("no corpus case pins a prompt, so the pin comparison checked nothing")
    return errors
