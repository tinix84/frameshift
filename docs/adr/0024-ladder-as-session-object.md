# ADR-0024: The ladder is a session object; held frames are adopted; selection needs two to five distinct candidates

- Status: accepted
- Date: 2026-10-06
- Deciders: repository owner, through the design conversation for #7
- Supersedes: none

## Context

`CONTEXT.md` defines the abstraction ladder as a chain of rungs, each recording
scope, boundary, measures, assumptions, and what is lost by moving level, and
ADR-0011 makes that recorded loss the thing that keeps the ladder honest.
Nothing in canonical state can hold it: the v2 frame has an
`abstraction_level` but no loss, and no event records a rung.

ADR-0021 says framing inherits the intake engine result's held ladder and frame
proposals rather than re-running the engine. Two facts stand against that as
built. `admit_result` returns the held proposal ids and keeps nothing, so the
proposals are gone once the call ends. And by the time intake is sealed the
result is necessarily stale, which `proposals.py` refuses to commit as though
it were current.

#7 asks for two to five materially distinct candidate frames, and nothing
checks either the count or the distinctness.

## Decision

**The ladder is its own object, grown by a new event.** The v2 session gains an
optional `ladder`: an array of rungs. A rung carries a session-local id with the
new `rung_` prefix, an `abstraction_level` from the existing closed set, the
outcome served at that level, its scope, a `system_boundary`, success measures,
assumptions, the loss incurred by moving to that level, and provenance. One
event type, `ladder.rung.recorded`, carries a whole rung. Recording a rung under
an id that exists replaces it, so a correction is another recording and the
earlier one stays in the history, as ADR-0021 does for classifications. At
most one rung stands at each level, and the ladder's order is the level's rank,
never insertion order. Rungs are recorded in the `framing` phase only. The
application reducer and the reference reducer learn the event in the same
commit, and a v2 history fixture exercises it, as ADR-0013 requires.

**Held proposals are kept and adopted, never committed stale.** The coordinator
keeps the last held engine result per session in memory, as it already keeps
pending confirmations: a restart forgets it, and a human re-runs the engine or
re-reads. The view shows the held ladder and frame proposals. A person adopts
one by issuing the ordinary command (`propose_frame`, or recording a rung),
pre-filled from the proposal and edited as they see fit. Nothing from a stale
result is committed without a human command, so the staleness rule stands
unchanged. A `problem_frame` proposal's value is read as the frame's own
fields; the frame it becomes is validated against the session schema like any
other.

**Selecting a frame needs two to five distinct candidates.** The
`frame_selection` gate refuses unless the session holds between two and five
live candidate frames (status `proposed` or `working`), no two of which agree on
outcome, abstraction level, and system boundary together. Outcomes are compared
after trimming and case folding. This is a precondition on the sealing command,
not a replay invariant: a history that passed the gate under the earlier rule,
the reference history included, still folds.

## Consequences

The ladder can be read, corrected, and audited apart from the frames, and the
loss at each level has a field rather than a convention. The cost is the
lockstep change ADR-0021 deferred: a new event type in both reducers, a new
provenance namespace in the `CONTEXT.md` registry and its mirror in the
evaluation harness, and a v2 history fixture.

The engine's `abstraction_ladder` proposal keeps its current value shape
(`levels`, `top_outcome`) and is only ever adopted by a person. Aligning the
published prompt contract to the rung shape is a prompt-contract change and
belongs with #87.

A frame has no provenance field, so an adopted frame does not cite the held
proposal it came from. Adoption is recorded as a human-authored proposal, which
is what it is.

A session cannot leave framing with one frame, nor with six. A reasoner who is
sure of their frame must still name an alternative, which is the point of
ADR-0011.

## Alternatives considered

- **Frames as the rungs, plus a loss field on the frame.** No new event type
  and no lockstep change. Rejected because it conflates two things a human
  approves separately: where the problem lives on the ladder, and which
  candidate is solved. Several frames can stand on one rung and differ only by
  boundary.
- **Persist engine results and allow a stale result to be admitted on
  acknowledgement.** Rejected because it weakens the staleness rule for the one
  case it most needs to cover: a result formed before the human corrected
  intake.
- **Re-run the engine at the start of framing.** Rejected because it discards
  work a human may want, contradicts ADR-0021, and leaves manual mode, which has
  no engine, without a path.
- **Report the count and distinctness without blocking.** Rejected because
  comparing alternatives is the product's purpose, and a warning on the one
  gate that ends framing would be easy to wave through.

## Validation

#7 owns the acceptance criteria and its slices own the evidence: both reducers
fold a v2 history containing `ladder.rung.recorded` events to the same state, and a
replaced rung keeps both recordings in the history; a second rung at an
occupied level and a rung citing an undeclared namespace are refused; held
proposals survive admission, are visible in the view, and are never committed
by admission itself; and the gate refuses one candidate, six candidates, and
two candidates that agree on outcome, level, and boundary, while the reference
history still folds.
