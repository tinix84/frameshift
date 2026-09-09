# ADR-0018: Correct the recorded scope of the frame migration decision

- Status: accepted; partially superseded by ADR-0019 (migration-history choice only)
- Date: 2026-09-09
- Deciders: repository approval invariant; correction of agent attribution
- Supersedes: ADR-0016 in part, its attribution of a specific migration disposition as accepted

## Context

Review of ADR-0016 against the owner comment in
[#86](https://github.com/tinix84/frameshift/issues/86#issuecomment-5575647203)
found that the record went beyond the approval it cited. The owner approved
the axis split and explicit, source-preserving migration with human review
of ambiguous conversions. The comment did not select the migration's session
history or its precise proposal and approval-record disposition.

## Decision

ADR-0016's paragraph beginning "Conversion does not transfer approval" contains
a proposed migration design, not an owner-approved implementation contract.
Its specific converted-frame disposition and reasoning-resumption procedure
remain pending. This correction does not change the existing approval-binding
invariant or authorize carrying an approval onto changed content.

The rest of ADR-0016's axis decision stands. No migration-history design is
selected here. Whether conversion continues the same session through an
explicit migration event or creates a linked session requires owner direction.

## Consequences

The original ADR text is retained for auditability. Migration implementation
and its acceptance evidence remain incomplete; schema and corpus checks alone
do not complete #86.

## Alternatives considered

- Rewrite the accepted record: obscures the attribution error.
- Treat an unanswered question as approval: violates the repository's human
  authority invariant.

## Validation

Compare recorded approval with #86's owner comment. Delivery evidence must
exercise the history and approval disposition once the owner selects it.
