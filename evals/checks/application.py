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

from . import canonical as reference


def application_encoder(case: dict, load) -> list[str]:
    """Compare the application encoder to the reference and to what is recorded."""
    from frameshift.persistence import canonical as application

    checkpoint = load(case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    if application.set_like_fields() != reference.SET_LIKE_FIELDS:
        errors.append(
            "the two encoders disagree about which arrays are sets: "
            f"application {sorted(application.set_like_fields())}, "
            f"reference {sorted(reference.SET_LIKE_FIELDS)}"
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
    reference_bytes = reference.encode(
        reference._order_sets(reference.canonicalize(checkpoint["state"]))
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
    if isinstance(value, str) and reference.TIMESTAMP.match(value):
        return value.lower()
    return value


def _reverse_keys(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


_PERTURBATIONS = {"key_order": _reverse_keys, "timestamp_spelling": _respell}
