# ADR-0004: Event history plus deterministic checkpoints

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

FrameShift needs auditability, revision conflict handling, rollback, and cross-runtime resume. Pure snapshots lose history; replaying every conversational turn is slow and nondeterministic.

## Decision

Persist immutable domain events with periodic state snapshots. Export portable deterministic checkpoints containing canonical state, event cursor, contract versions, capability profile, artifact references, and integrity digests.

## Consequences

Implementations must define event evolution, migrations, canonicalization, and retention. Restore can verify integrity and resume without provider history. Sensitive deleted content must not be retained merely for replay.

## Alternatives considered

- Snapshot only: simpler but weak audit and conflict explanation.
- Full event sourcing without snapshots: strong history but expensive restore and evolution.
- Transcript replay: nonportable and unsafe.

## Validation

Checkpoint hashes are stable, replay matches snapshot state, corruption is detected, and deletion policy covers events and derived data.
