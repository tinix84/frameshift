# ADR-0017: Validate prompts against published identities

- Status: accepted
- Date: 2026-09-09
- Deciders: repository owner, through the accepted contract handoff in #168
- Supersedes: none

## Context

Checking a body against its own manifest detects accidental edits, but accepts
a rewritten body if its author also recomputes the manifest digest. The accepted
prompt contract requires comparison against the published identity, retained
in executions and checkpoints. Input references must be resolved and bounded
before their content is released to a client.

## Decision

Release records pin each prompt ID and exact version to its published body
digest independently of the installed prompt file. Reviewed release records
are trusted configuration, not model-provided input. Publication adds a new
version; it never replaces an existing identity. Git history and versioned
release notes carry the reviewable change history.

An execution carries the exact ID, version and digest in its request and
completed record; checkpoints preserve that identity for earlier results.
Missing or mismatched identities block new reasoning, while authorized
inspection remains subject to the ordinary disclosure policy. Changing the
prompt version requires a recorded human approval; it cannot relabel a prior
result as having used the new prompt.

Reasoning context construction enforces the prompt's declared accepted input
types, aggregate UTF-8 input bytes and JSON depth before returning context.
The initial maximums are 1 MiB and depth 64; effective policy may tighten them.
The eight task-frame parts retain the separation of trusted instructions from
source-labelled untrusted content. Limits reject oversized input instead of
truncating it. They are validation ceilings, not a guarantee of model capacity.

## Consequences

Changing both an installed body and its self-declared digest cannot replace a
published prompt. This assumes the release registry is protected as trusted
application configuration; it does not defend against a compromised operator
rewriting the entire installation. Provider metrics and requested client
budgets remain separate from server-enforced input limits.

## Alternatives considered

- Trust the current manifest alone: cannot detect same-version rewriting.
- Hash the current prompt only when restoring: loses the identity used by an
  earlier execution and cannot establish reproducibility.
- Truncate or validate each referenced artifact separately: can silently omit
  evidence or exceed the aggregate budget.

## Validation

#168 owns implementation and positive/negative evidence for identity
substitution, same-version rewriting, missing prompts, aggregate overflow,
depth violations and preserved input boundaries. These checks establish
enforcement, not semantic compliance by a model.
