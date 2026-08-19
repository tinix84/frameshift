# ADR-0011: Problem framing is solution-neutral

- Status: accepted
- Date: 2026-08-19
- Deciders: initial maintainers
- Supersedes: none

## Context

A request usually arrives as a solution. "We need a 5 kW buck-boost DC/DC" is not a problem statement; it is one candidate answer with the problem removed. Analysing it faithfully produces a technically deep result in a strategically narrow space, because the choices available at component level are a small subset of those available at the level where the problem actually lives.

Four structures make that failure detectable instead of invisible: classifying what kind of statement arrived, recognising a solution wearing a problem's clothes, walking the abstraction ladder to find where the problem lives, and naming the system boundary the frame assumes. `CONTEXT.md` defines all four as vocabulary. None is recorded as a decision, so nothing states that they are required, closed, or falsifiable.

This ADR fills the framing engine of ADR-0010.

## Decision

**Every authored statement carries exactly one primary role** from a closed set: `observation`, `need`, `outcome`, `problem`, `function`, `requirement`, `constraint`, `assumption`, `proposal`, `question`. Human wording is preserved verbatim and classification is always correctable — the classification is FrameShift's reading, never a rewrite of what the person said.

**A statement that names a component, topology, vendor, or action while omitting the outcome it serves is a solution in disguise.** Detecting one obliges the framing engine to abstract upward before the statement is accepted as a frame. It is never silently discarded: it is retained as a candidate option under its own frame, so reframing widens the space without throwing away the answer the user brought.

**Frames are organised on an abstraction ladder.** *Why* moves toward outcomes, *how* toward mechanisms. Each rung records scope, boundary, measures, assumptions, and what is lost by moving level — that last field is the one that makes the ladder honest, since moving up is not free.

**Every frame declares a system boundary** from a closed set: component, subsystem, product, lifecycle, operations, supply chain, portfolio, business model. Two frames at the same abstraction level with different boundaries are different frames.

**Candidate frames coexist; only human approval makes one working.** The engine presents alternatives at more than one level and never silently selects the level itself. A session has at most one working frame, and the frames not chosen are retained rather than deleted.

## Consequences

Reframing is auditable: the ladder shows where a problem was found, what was given up climbing to it, and which candidate frames were rejected. The DC/DC is not lost; it is repositioned as one leaf among many means to a higher objective.

Both closed sets are now load-bearing. A role or boundary the domain needs but the set lacks is a superseding ADR, not a new enum value. Statement roles overlap graph node types (ADR-0003) without being identical, and that distinction has to be maintained deliberately.

Framing costs a turn before analysis begins, and for a correctly-framed request it buys nothing.

This ADR records the structures, not their enforcement. Whether a frame is schema-invalid until these fields are populated, whether a human may skip the check, and whether a frame also carries a time scale are open and decided elsewhere.

## Alternatives considered

- Accept the user's statement as the problem: fastest and most respectful of expertise, but collapses the solution space before anyone notices it was collapsed.
- Always abstract to the business level: maximises options but discards genuine constraints and produces frames nobody can act on.
- Free-text frames with no roles or boundary: preserves nuance, but nothing is checkable and two frames cannot be compared.
- Fold statement roles into graph node types: one fewer vocabulary, but conflates what a person said with what the causal model asserts.

## Validation

Fixtures cover solution-in-disguise detection, ladder construction with a recorded loss per rung, and frames that differ only by system boundary. Every statement resolves to exactly one role; classification is correctable without losing the original wording. Causal reasoning cannot begin without an approved working frame, and rejected candidate frames survive in state.
