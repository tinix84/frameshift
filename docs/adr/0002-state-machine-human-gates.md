# ADR-0002: Explicit state machine and human gates

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

Conversational approval is ambiguous, and model proposals can appear authoritative. Problem boundary, evidence sufficiency, values, and consequential actions require accountable human judgment.

## Decision

Use an explicit workflow state machine. Engines only propose artifacts. Frame selection, evidence sufficiency, option-set acceptance, criteria confirmation, decisions, consequential tool actions, and knowledge promotion require typed human dispositions bound to content digest and session revision.

## Consequences

Interaction adds friction at meaningful points and cannot be fully autonomous. Approval is auditable, stale proposals are detectable, and runtimes cannot silently advance phases.

## Alternatives considered

- Infer approval from natural language: smoother but ambiguous and unsafe.
- Require approval for every generated item: safe but unusably granular.

## Validation

State-transition tests reject missing, unauthorized, stale, and digest-mismatched approvals.
