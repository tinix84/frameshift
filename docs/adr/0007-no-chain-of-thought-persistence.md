# ADR-0007: Do not persist private chain-of-thought

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

FrameShift needs explainability and audit without depending on inaccessible, unstable, potentially sensitive internal model reasoning.

## Decision

Persist only user-auditable rationale summaries, cited inputs, assumptions, alternatives, uncertainty, tool traces, and decision records. Do not request, expose, log, or checkpoint private chain-of-thought.

## Consequences

Explanations focus on inspectable artifacts and provenance. Debugging uses structured execution metadata and fixtures rather than hidden reasoning. The product does not claim complete transparency into model internals.

## Alternatives considered

- Persist all reasoning tokens: creates privacy, portability, and reliability problems.
- Persist no rationale: protects internals but leaves users unable to audit transformations.

## Validation

Prompts, schemas, logs, and fixtures contain rationale-summary language and no chain-of-thought fields.
