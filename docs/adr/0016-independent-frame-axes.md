# ADR-0016: Separate frame abstraction from system boundary

- Status: accepted; partially superseded by ADR-0018 (migration-disposition attribution only)
- Date: 2026-09-09
- Deciders: repository owner, through the frame-axis decision in #86
- Supersedes: none

## Context

The original session schema mixes ranked abstraction levels with lateral
system boundaries. A ceiling over that mixed set invents an ordering between
operations, supply chain and product. The glossary and ADR-0011 already treat
abstraction and boundary as distinct attributes. The owner approved the exact
split and preservation of existing checkpoints in
[#86](https://github.com/tinix84/frameshift/issues/86#issuecomment-5575647203).

## Decision

A frame carries both a ranked abstraction level and an unranked system
boundary. The schema owns their closed value sets. Boundary widening alone
does not raise abstraction. Ceiling comparisons use only abstraction level.

The required boundary field makes this session contract version 2. Existing
version-1 checkpoints keep their original schema interpretation and digests.
Conversion is explicit and creates a separate checkpoint referencing its
source. Missing or ambiguous axes are reported for human review; the converter
never maps a lateral legacy value to a supposedly higher abstraction level.

Conversion does not transfer approval to changed frame content. The source
checkpoint preserves the original approved state. Converted frames return as
proposals for review; historical approval records keep their original digests
and revisions. The converted checkpoint cannot advance reasoning until frame
selection is confirmed against its new content. Conversion is not an event-log
replay or permission to rewrite the original history.

Temporal properties remain descriptive properties under #59 and cannot enter
either enum. Their contract handoff and the framing-gate policy in #64 are
separate from this axis split; this change does not invent temporal values.

## Consequences

New readers explicitly support both schema versions; a version-1 reader cannot
accept a version-2 write. The legacy reference remains the digest golden, and
a separate migrated reference exercises conversion and new frame constraints.
An implementation must preserve the original artifact, never overwrite it.

## Alternatives considered

- Rank the mixed enum: assigns meaning to a lateral boundary change.
- Add a required field under version 1: breaks strict readers silently.
- Infer absent boundaries or copy approvals onto new digests: invents a human
  choice and violates the existing approval-binding rule.

## Validation

#86 owns delivery: independent axes, exact ladder drift checks, explicit
conversion with source preservation, ambiguous mappings requiring review,
rejection of unsupported versions, and stale approval after conversion.
The corpus retains refusal ceilings while expressing boundaries separately.
