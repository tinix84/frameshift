# ADR-0019: Migrate frame axes into a linked session

- Status: accepted
- Date: 2026-09-09
- Deciders: repository owner, through the implementation continuation for #86
- Supersedes: ADR-0018 in part, its deferral of the migration-history choice

## Context

ADR-0016 separates abstraction level from system boundary and requires explicit,
source-preserving conversion of version-1 checkpoints. ADR-0018 corrected an
unsupported claim about conversion history and left two alternatives open:
continue the existing session with a migration event, or create a linked
session under the new contract.

Mixing two incompatible session schema majors in one event history would make
replay depend on a schema-changing event and complicate the meaning of revision
numbers. A linked session can use one schema version throughout while retaining
an inspectable connection to the exact source checkpoint.

## Decision

Frame-axis conversion creates a new version-2 session and a separate
version-2 checkpoint. Both receive new identifiers. The migrated checkpoint
records the source checkpoint identifier, digest and schema version. The source
artifact is input only: conversion never overwrites it or changes its recorded
digests.

The linked session begins a new event history and revision sequence. Its source
reference supplies lineage, not inherited authority. The still-unresolved
disposition of converted frame status and historical approval records remains
outside this decision until the owner selects it.

## Consequences

Readers never need to replay one session across incompatible schema majors.
Auditors can recover the exact source artifact from the migration reference,
and conversion can be retried without changing that source. Session identifiers,
revisions and approvals from the source cannot be mistaken for records created
under the version-2 contract.

## Alternatives considered

- Continue the same session with an explicit migration event: preserves one
  event stream, but makes replay cross a schema-major boundary and overloads
  revision continuity with contract conversion.
- Rewrite the existing checkpoint in place: loses the preserved source and is
  incompatible with ADR-0016 and the API compatibility contract.

## Validation

#86 owns migration fixtures proving distinct session and checkpoint identities,
source lineage, source immutability, version-2 schema validity, unsupported
version refusal and human review for ambiguous axis mappings.
