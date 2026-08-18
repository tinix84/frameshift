# Persistence and memory model

## Principle

FrameShift remembers explicit artifacts, not hidden reasoning. Conversation is an input channel; the canonical memory is a versioned session state with provenance and approvals.

## Memory layers

| Layer | Lifetime | Contents |
|---|---|---|
| Turn context | One execution | Relevant commands, bounded state slice, tool results |
| Working state | Active session | Candidate frames, graph proposals, pending approvals |
| Durable session | Retention policy | Approved state, events, evidence references, decisions |
| Workspace knowledge | Explicit promotion | Reusable glossary, policies, validated patterns |
| Evaluation corpus | Separate governance | Synthetic/redacted fixtures and expected invariants |

Nothing moves from a session to workspace knowledge without an explicit promotion command and permission check.

## Event model

Events use an envelope with event ID, session ID, sequence, prior revision, actor, type, schema version, payload, timestamp, idempotency key, causation ID, and correlation ID. Representative types include:

- `intake.recorded`
- `statement.classified`
- `frame.proposed`
- `frame.approved`
- `hypothesis.proposed`
- `evidence.attached`
- `option.proposed`
- `assessment.recorded`
- `decision.approved`
- `checkpoint.created`
- `artifact.redacted`
- `session.deleted`

## Snapshots and checkpoints

- Snapshot every configurable event count or phase transition.
- A checkpoint packages normalized state, event cursor, schema versions, engine versions, prompt IDs, capability profile, and digests.
- Transient timestamps, token counts, and provider request IDs live in execution metadata and do not affect the state digest.
- Restore verifies all digests, validates schemas, then replays post-snapshot events.

## Merge and concurrency

Commands include `expected_revision`. Conflicting writes are rejected with the current revision and a conflict description. Proposal branches may be merged by stable object ID; contradictory semantic changes require human resolution. Approval objects are never auto-merged.

## Retention and deletion

Workspaces set retention by data class. Deletion tombstones the aggregate, revokes access, schedules encrypted blobs and derived indexes for deletion, and records a minimal non-sensitive audit proof when legally permitted. Backups follow a documented expiry window. Exports and external tool copies are disclosed because FrameShift cannot erase systems it does not control.

## Retrieval

Retrieval is scoped by workspace, session, permissions, data class, and purpose. Results include provenance and relevance; retrieved content is untrusted. Semantic indexes are derived data and must follow source retention and deletion.

## Migration

Schemas are forward-versioned. Readers must reject unknown breaking major versions. Migrations are deterministic, idempotent, tested on fixtures, and preserve the original artifact digest in migration provenance.
