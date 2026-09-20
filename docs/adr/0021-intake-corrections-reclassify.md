# ADR-0021: Intake corrections reclassify; nothing rewrites a statement

- Status: accepted
- Date: 2026-09-20
- Deciders: repository owner, through the design conversation for #6
- Supersedes: none

## Context

CONTEXT.md promises that a statement's human wording is preserved and its
classification is correctable, and names intake correction as the checkpoint
gate between the intake and framing phases. Until #6 nothing implemented
intake, so the promise had no mechanism: there was no place a request became a
session, no record of how it was classified, and no way to correct a
classification that could be audited afterwards.

Three forces constrain how correction is recorded. ADR-0013 fixes the event
vocabulary as something that grows deliberately — an unknown event type is a
hard error in the reducer, and the evaluation harness carries a reference
reducer that reads the same committed history, so any change to the vocabulary
must move reference and application together. ADR-0011 requires that a request
naming a component, vendor, or action without the outcome it serves be
detected as a solution in disguise and drive upward abstraction. And the
published problem-framing prompt contract already performs classification, the
why/how ladder, and candidate frames as one bounded engine step, while the
tracker splits that work across #6 and #7.

## Decision

**A correction is a reclassification.** A human correction of a statement's
roles emits `statement.classified` again, with the new primary and secondary
roles. The committed vocabulary contains no event that changes a statement's
`text`, so original wording is preserved by construction rather than by rule,
and every earlier classification remains in the history as the record of what
was corrected. Neither the vocabulary nor the `statement.classified` payload is
extended for this; attributing a correction to an actor is a separate,
deliberate vocabulary change (#230).

**Every intake command is an atomic revision-bound commit.** Opening a
session, admitting classifications, and correcting one each emit a batch of
events, and the last event of the batch carries the new revision; session
creation carries revision zero. This is the pattern the committed reference
history follows, and it keeps revision — optimistic concurrency — distinct from
phase, which advances only through a checkpoint gate.

**Solution-in-disguise detection is derived from state, not recorded as an
event.** Whether upward abstraction is required is a pure function over the
folded session: an intake statement whose primary role is `proposal` with no
`outcome` statement serving it. No event type is added to say so.

**One engine, two slices of admission.** Intake reuses the published
problem-framing prompt contract and admits only its `statement_classification`
proposals; abstraction-ladder and problem-frame proposals are held readable and
unapplied until framing admits them. No intake prompt contract, manifest, or
engine enum value is introduced.

**Sealing intake is the existing gate.** `intake_correction` is the
intake-to-framing checkpoint gate. Its approval binding, trusted-confirmation
requirement, and emitted events are already implemented; intake appends those
events and adds no approval logic of its own.

## Consequences

Wording can never be lost to a correction, and the audit of a correction is a
diff of the history rather than a comparison of two snapshots. Corrections are
auditable by order and content but not, in this slice, by author.

The event vocabulary and the reference reducer are untouched, so replay
conformance holds without a lockstep change, and #6 can land without reopening
the vocabulary. The cost is deferred: #230 must decide how an actor is recorded
and change reference and application in one commit.

Detection needs no new event but must be recomputed from state wherever it is
shown; it cannot be read off the log directly.

Framing (#7) inherits an engine result whose ladder and frame proposals are
already present and held, rather than re-running the engine to obtain them.

## Alternatives considered

- **A distinct correction event carrying the actor.** Cleanest audit story;
  rejected here because it is a new event type that both reducers must learn in
  the same commit, which is exactly the lockstep change the deadline cannot
  absorb. Recorded as the leading option on #230.
- **Extending the `statement.classified` payload with an actor.** Smaller than a
  new type, but still a change to a committed payload the reference reducer
  reads, and it blurs first classification with correction. Deferred to #230.
- **Correction as supersession** — a new statement with the corrected role,
  the old one marked `superseded`. Rejected because it duplicates the text into
  a second statement and makes "the request" two things, when the glossary
  says a statement's wording is preserved and its classification corrected.
- **A dedicated intake prompt contract and engine.** Rejected because the
  engine enum has four values and none is intake, the published framing
  contract already performs the step, and a second contract would need its own
  manifest, digest, and fixtures for work the first already does.
- **Recording detection as an event.** Rejected because it adds a vocabulary
  type for a fact that is fully determined by state already in the log.

## Validation

#6 owns the acceptance criteria and its tickets own the evidence: the
application reducer folds the committed reference history to the reference
checkpoint's exact state digest (#225); a correction folds to the last roles
with the text byte-identical, with both classification events retained, and a
new `replay_equivalence` fixture pins that behaviour (#228); detection is
required for the reference history's own prismatic-cells statement and not
once an outcome statement exists (#228); and the folded session reaches phase
`framing` only through the existing gate (#229).
