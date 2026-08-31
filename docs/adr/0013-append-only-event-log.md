# ADR-0013: The first slice's event log is append-only JSON lines

- Status: accepted
- Date: 2026-08-31
- Deciders: initial maintainers
- Supersedes: none

## Context

ADR-0004 persists immutable domain events with periodic state snapshots and promises that restore replays post-snapshot events. It does not say what the log physically is, and that gap blocked more than storage: the replay-equivalence conformance ticket could not be written, because what a replay fixture looks like depends on whether events are lines in a file or rows in a table.

ADR-0008 asks for local files first and a database later "without changing contracts". Whether that later swap is real or theoretical is the question this decision actually answers.

Two properties of this repository constrain the choice more than performance does. The evaluation harness and `scripts/validate_repo.py` are stdlib-only, so anyone can clone and verify with no install. And every fixture is a committed text artifact a reviewer can read in a diff — that is how the corpus stays reviewable rather than merely runnable.

## Decision

**The first slice's event log is append-only JSON lines: one event per line, UTF-8, in sequence order.**

**Every event carries a monotonic `sequence` starting at one.** The sequence is the log's own ordering and the checkpoint's `event_cursor` names the last sequence a snapshot covers. A log whose sequences skip, repeat, or run out of order is refused before it is folded, because an append-only log that failed to append in order is not a log with a gap — it is a log that cannot be trusted to be the history.

**Session revision is not the event sequence.** Sequence advances on every event; revision advances only on committed transitions, and an event carries a `revision` only when it moves one. Conflating them would make every internal event look like a human-gated commit.

**A snapshot is a cache of the fold, never an independent record.** Folding the log must reproduce the snapshot's `state_digest` exactly. Where the two disagree, the log is the history and the snapshot is wrong.

The storage engine may later become SQLite or Postgres. What may not change is the contract above: events are immutable, ordered by a monotonic sequence, and fold to the snapshot. That is what makes the swap real rather than theoretical — a later engine is measured against the same replay fixtures.

## Consequences

Replay equivalence becomes testable now, with no dependency and no service. `evals/fixtures/reference.events.jsonl` folds to the committed reference checkpoint's exact `state_digest`, and the reducer is a separate code path from the state document, so drift between event handlers and state shape fails a test rather than surviving to production.

A reviewer can read the history in a diff. That matters more in the first slice than indexed queries do, because the thing being reviewed is whether the event model is right at all.

The costs are real and accepted. There is no transactional append, no index, and no concurrent writer story; a large log is read whole. Each is a reason to move to a database later, and none of them bites at the size a single reasoning session reaches.

Compaction, retention, and log rotation are not decided here. Neither is the full domain event vocabulary — the reducer implements the types the reference session needs, and an unknown type is an error rather than a silent skip, so the vocabulary grows deliberately.

## Alternatives considered

- **SQLite.** Still stdlib, gives transactional appends and indexed reads, and is closer to what a real runtime wants. Rejected for the first slice because a binary fixture cannot be diffed, which would make the one artifact the whole replay property rests on unreviewable.
- **Postgres.** Named in the founding material. Adds a service to a repository whose evaluation story is "clone and run", for throughput nobody has yet needed.
- **Snapshots only, no event log.** Simplest, and ADR-0004 already rules it out: without history there is nothing to replay, and a corrupted snapshot has no second source to check against.

## Validation

`replay-reproduces-the-snapshot` folds the committed log and asserts it reaches the reference checkpoint's recorded `state_digest`, and that the log's length matches the snapshot's `event_cursor`. `replay-with-a-dropped-event-diverges` and `replay-out-of-order-is-refused` assert the property can fail: a truncated log reaches a different digest, and a reordered one is refused before folding.
