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

from . import canonical as reference_canonical
from . import schema as reference


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
