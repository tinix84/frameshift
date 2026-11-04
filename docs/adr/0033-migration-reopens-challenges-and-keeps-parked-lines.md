# ADR-0033: Migration reopens every closed challenge and carries parked lines as they are

- Status: accepted
- Date: 2026-11-04
- Deciders: repository owner, through the design decision on #284
- Supersedes: none; extends ADR-0025 to the session objects of ADR-0031 and ADR-0032

## Context

ADR-0019 makes a linked session from a source checkpoint. ADR-0020 and
ADR-0025 make sure that the linked session carries no authority: every
decided status becomes `proposed`, and no approval record is copied.

ADR-0031 and ADR-0032 add two session objects that ADR-0025 does not name:

- A challenge (`state.challenges`) is `open`, `answered` or `conceded`. Any
  boundary may raise one. Only the person answers or concedes one. An answer
  and a concession each name the person's actor.
- A parked line (`state.lines`) is `parked` or `reopened`. Only the person
  parks or reopens one. ADR-0032 calls parking a disposition about effort, not
  a verdict on truth. Parking changes no status, and it never gates.

The migration code deep-copies the source state. Without a rule, a linked
session would hold answers, concessions and parked lines that the source
person recorded in a different session.

Today no challenge or line can cross. Migration accepts only schema `1.0.0`
sources, and the version-1 session schema has no `challenges` and no `lines`.
A version-1 source that holds them is refused with `schema_invalid`. The rule
is for the first migration that can take a later source. ADR-0029 handled
`superseded_by` in the same way.

## Decision

**A closed challenge reopens in the linked session.** An `answered` or
`conceded` challenge becomes `open`. Migration removes its `answer` or its
`concession`. The id, the target, the objection and the actor who raised it
stay. An `open` challenge crosses unchanged.

The answer and the concession are the person's judgement. A judgement needs
its record in the session that holds it. This is the rule of ADR-0025, applied
to a challenge. A raise decides nothing (ADR-0031), so the objection crosses.

**A parked line crosses as it is.** Migration copies every line, `parked` or
`reopened`, with every field. A line is a disposition about effort and holds
no authority. Its reason text is the thread that the person reads when they
come back (ADR-0032). The linked session keeps that thread on its canvas.

The source checkpoint stays the record of every answer and concession that
migration removes.

## Consequences

The linked session asks the person again to close each challenge. Until the
person answers, every node with a reopened challenge on it is weak, and every
node above that node has an open challenge upstream (ADR-0031). This is the
same cost that ADR-0025 accepts for decided statuses.

The person can close a reopened challenge in the linked session. The answer
and concede commands of ADR-0031 accept an `open` challenge.

A parked line in the linked session names an actor from the source session.
The person can reopen the line in the linked session, as in any session.

## Alternatives considered

- **Keep every challenge and line unchanged.** An answer or a concession
  would then stand in a session that holds no record of it. That breaks
  ADR-0025.
- **Reset the challenges and drop every line.** Only the person parks, so
  the argument for authority applies to a line too. But parking holds no
  authority, and the linked canvas would lose each dead end and its reason.
- **Drop every challenge and every line.** Raising decides nothing, so an
  open doubt would be lost without reason.
- **Write the rule only when a later migration exists.** The reset of
  `superseded_by` (ADR-0029) set the precedent. The migration code carries
  the rule now, so that a later source cannot skip it.

## Validation

#284:

- the reset step reopens an `answered` and a `conceded` challenge, removes
  the answer and the concession, and keeps every other field;
- an `open` challenge crosses unchanged;
- a `parked` and a `reopened` line cross unchanged;
- a version-1 source that holds `challenges` or `lines` is refused with
  `schema_invalid`, and no checkpoint is written.
