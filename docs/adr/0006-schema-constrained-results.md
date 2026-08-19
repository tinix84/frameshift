# ADR-0006: Schema-constrained engine results

- Status: accepted; superseded in part by ADR-0009 (constraint moves to the tool input schema and repair narrows; the EngineResult envelope stands)
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

Free-form model output is hard to merge, validate, evaluate, or transfer. Not every runtime supports native structured output, and probabilistic responses can still violate semantics.

## Decision

Every reasoning engine returns a versioned `EngineResult` containing typed proposals, rationale summaries, uncertainty, conflicts, missing information, capability requests, and required checkpoints. Use native constrained output when available, otherwise JSON extraction plus one shape-only repair. Validate domain invariants outside the model.

## Consequences

Prompt and schema versions evolve together. Some expressive prose moves to derived views. Invalid output fails safely instead of being implicitly accepted.

## Alternatives considered

- Parse Markdown conventions: flexible but brittle.
- Let adapters define outputs: faster per adapter but destroys portability.

## Validation

All adapters pass valid, invalid, repairable, and unrepairable result fixtures without creating new facts during repair.
