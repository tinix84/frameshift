"""The phase machine and the gates between phases (#3, ADR-0002).

ADR-0002 says a phase cannot advance without a typed human disposition bound to
a content digest and a session revision. The approval guard in the harness
already refuses every way that binding can be wrong, and it is the reference an
orchestrator is measured against.

It does not, however, check *where you are standing*. `attempt_transition`
validates the approval and the target and then accepts, whatever phase the
session is in — so a correctly-signed `decision_approval` presented during
intake is accepted today. Binding and sequence are two different guards, and
only one of them existed.

This is the other one. A gate is legal only from the phase it belongs to, and
it leads to exactly one phase. Both facts come from the committed approval
fixtures rather than from an opinion formed here: every `(gate, to_phase)` pair
below appears in `evals/fixtures/approval-*.case.json`, and
`frameshift/tests/test_phases.py` asserts the table still matches them.

Two gates do not advance anything. `external_action` and `knowledge_promotion`
guard an act inside a phase, not a boundary between phases — CONTEXT.md calls
every gate "a phase boundary", which is true of six of the eight. Naming that
here is cheaper than discovering it in an orchestrator that expected all eight
to move something.
"""

from __future__ import annotations

from dataclasses import dataclass

# The session phases, in the order the reasoner walks them. Mirrored from the
# `phase` enum in `schemas/session.schema.json`, which is the structural
# authority; a test asserts the two still agree.
PHASES = ("intake", "framing", "causal", "solutions", "decision", "monitoring")


@dataclass(frozen=True)
class Gate:
    """One checkpoint gate: where it may be passed, and where it leads."""

    name: str
    from_phase: str
    to_phase: str

    @property
    def advances(self) -> bool:
        """False for a gate that guards an act inside a phase rather than a boundary."""
        return self.from_phase != self.to_phase


# The eight gates CONTEXT.md names, each with the phase it is passed from and
# the phase it leads to.
GATES = {
    gate.name: gate
    for gate in (
        Gate("intake_correction", "intake", "framing"),
        Gate("frame_selection", "framing", "causal"),
        Gate("evidence_sufficiency", "causal", "solutions"),
        Gate("external_action", "causal", "causal"),
        Gate("option_set_acceptance", "solutions", "decision"),
        Gate("criteria_confirmation", "solutions", "decision"),
        Gate("decision_approval", "decision", "monitoring"),
        Gate("knowledge_promotion", "monitoring", "monitoring"),
    )
}


def gates_from(phase: str) -> list[str]:
    """The gates that may be passed while standing in `phase`."""
    return sorted(name for name, gate in GATES.items() if gate.from_phase == phase)


def legal_target(gate_name: str, phase: str) -> str | None:
    """The phase this gate leads to from `phase`, or None if it cannot be passed here."""
    gate = GATES.get(gate_name)
    if gate is None or gate.from_phase != phase:
        return None
    return gate.to_phase


def advance(phase: str, gate_name: str, to_phase: str | None = None) -> list[str]:
    """Refusals for one attempted transition, ignoring the approval itself.

    Returns an empty list when the sequence is legal. This says nothing about
    whether an approval was supplied or bound correctly — that is ADR-0002's
    binding guard, and a transition must satisfy both.
    """
    if phase not in PHASES:
        return [f"invariant_violation: unknown phase {phase!r}"]
    gate = GATES.get(gate_name)
    if gate is None:
        return [f"invariant_violation: unknown gate {gate_name!r}"]
    if gate.from_phase != phase:
        return [
            f"invariant_violation: gate {gate_name} is passed from {gate.from_phase!r}, "
            f"and the session is in {phase!r}"
        ]
    if to_phase is not None and to_phase != gate.to_phase:
        return [
            f"invariant_violation: gate {gate_name} leads to {gate.to_phase!r}, "
            f"not {to_phase!r}"
        ]
    return []
