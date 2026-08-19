# ADR-0010: Four reasoning engines, framing first

- Status: accepted
- Date: 2026-08-19
- Deciders: initial maintainers
- Supersedes: none

## Context

`CONTEXT.md` defines a **reasoning engine** as "one of four bounded producers of proposals: problem framing, causal reasoning, solution generation, decision and validation". The founding sessions treat that pipeline as the central architecture and argue its ordering is the point: *before answering the question, challenge whether the question is being asked at the right level.*

`CONTEXT.md` is definitions-only by its own charter — durable decisions live here. So the spine of the product has been carried as vocabulary, with nothing recording that it is a decision, what it rules out, or what would falsify it. This ADR fixes that. It does not invent anything; it makes an existing arrangement accountable.

## Decision

Reasoning is decomposed into exactly four bounded engines, in this order:

1. **Problem framing** — produces candidate problem frames. See ADR-0011.
2. **Causal reasoning** — produces the typed causal model of ADR-0003.
3. **Solution generation** — produces options against leverage points.
4. **Decision and validation** — produces assessments and a decision record.

**The order binds.** Causal reasoning operates against an approved working frame. A session cannot reach it without one, so a request that arrives already phrased as a solution is reframed before it is analysed rather than after.

**Four is closed.** Adding, removing, or splitting an engine is a superseding ADR, not a refactor. This is what keeps the count from drifting under local pressure.

**An engine boundary is enforceable, not conceptual.** Each engine is one module with an architecture-test-enforced dependency rule, one prompt-contract namespace, and one MCP tool group under ADR-0009. An engine consumes a bounded reasoning context and returns an `EngineResult` (ADR-0006). It cannot persist state, call an ungranted tool, or invoke another engine.

**Engines only propose.** Each transition between engines is a checkpoint gate under ADR-0002 requiring a typed human disposition.

Explorer, critic, question-selection, and reflection are *phases within* an engine's prompt contract, not engines. They may share one underlying model with different prompts.

## Consequences

The pipeline is legible in the module layout, the tool namespace, and the state machine, and an architecture test can name what it enforces — which is what makes this ADR verifiable rather than descriptive.

Work that does not fit one of the four engines has nowhere to go without a superseding ADR. That friction is intended: it is the mechanism that stops the reasoning surface from growing by accretion.

Framing-first adds a gate before a user gets an answer. For a user who already knows their frame, this is pure cost. Whether a human may fast-path that gate, and what the gate must check, is deliberately left open — it is decided separately, against the framing engine's obligations.

Two questions this ADR does not settle and must not be read as settling: whether a derived score may order or gate engine behaviour, and what slice of the graph becomes an engine's reasoning context.

## Alternatives considered

- One general reasoning engine with a phase parameter: fewer moving parts, but no enforceable boundary, no per-engine contract versioning, and nothing to stop causal reasoning from silently reframing.
- An open set of engines: flexible, but the count drifts and the state machine stops being a fixed graph.
- Framing as an optional preprocessing step: cheaper for expert users, but abandons the founding claim, since the frame is exactly what a user in a hurry gets wrong.
- Decompose by role instead — explorer, critic, question-selector, reflection: a real decomposition, but orthogonal to the domain phases and unable to carry the state machine's gates.

## Validation

Architecture tests enforce that no engine module imports another and that each engine's tools live in its own namespace. State-transition tests reject causal-reasoning entry without an approved working frame. Every prompt contract resolves to exactly one engine. A fifth engine cannot be introduced without a superseding ADR.
