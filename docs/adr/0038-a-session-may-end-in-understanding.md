# ADR-0038: A session may end in understanding; the person disposes each leaf and signs a closing statement that lists the open ones

- Status: accepted
- Date: 2026-11-11
- Deciders: repository owner, through the design grilling of 2026-11-11 on the source-page vision, recorded in [#302](https://github.com/tinix84/frameshift/issues/302)
- Supersedes: none; builds on ADR-0002, ADR-0031, ADR-0032 and ADR-0035

## Context

Every journey ends today in a signed decision record. A person who studies
a transcript, or who wants to understand a failure before anyone asks for a
fix, has no decision to sign. To finish, they would have to invent options
and compare them.

The person's own test for "done" is that every branch reaches something
they understand. ADR-0031 derives how well a node is grounded, and states
that grounding orders and informs and never gates.

## Decision

**A session has a second ending.** The person can close a session in
understanding. This ending needs no working frame, no option and no
decision record. It is one session kind with two endings, not a second
session kind.

**A leaf is a live graph node that no other live node supports.**

**The person gives a leaf a disposition.** The set is closed:

| Disposition | Meaning |
|---|---|
| `understood` | the person states it in their own words |
| `accepted_as_assumption` | the person goes no deeper and says so |
| `parked` | the leaf is on a parked line, with its reason (ADR-0032) |

A disposition is about the person's understanding, not about truth. It
changes no status and no provenance kind. No reasoner-facing boundary
exposes it.

**The person closes with a closing statement.** It is the person's own
words on what they now understand. The closing record lists every leaf
that has no disposition at that revision.

**Closing in understanding is a checkpoint gate.** The approval needs the
closing statement, never pre-filled from a reasoner's text (ADR-0035). It
binds under the approval profile in force. No reasoner-facing boundary
exposes it.

**Open leaves do not block the gate.** The person can close with leaves
that have no disposition. The record shows them.

**The person can reopen the session.** Every disposition and the earlier
closing statement stay in the history.

## Consequences

A study session ends without invented options. The decision ending is
unchanged.

What the person signs says how far they went. A reader of the record sees
the leaves that stayed open, and sees which leaves rest on an accepted
assumption.

The person can mark a leaf `understood` without understanding it. The
system does not test the claim. The person's own words are on the record,
as they are at the two hard gates of ADR-0035.

A session closed in understanding has no decision record to export. The
closing statement and the graph are its outputs.

## Alternatives considered

- **"I now understand X" as the decision.** It keeps one ending. But a
  decision record needs options and a comparison, so the person would
  invent them.
- **A separate session kind for study.** It can have its own shorter column
  set. But it splits the product before the two paths differ in more than
  their last step.
- **A leaf counts only when it is a fact.** It is strict. But it turns
  grounding into a gate, against ADR-0031, and blocks a session on the
  first claim that nobody can source.
- **Every leaf needs a disposition before the session closes.** It is
  complete. But it invites the person to mark forty leaves `understood` to
  get out.

## Validation

[#297](https://github.com/tinix84/frameshift/issues/297) owns the
implementation and its evidence: a session with no working frame, option or
decision record closes through the new gate; the gate refuses an empty or
pre-filled closing statement; the closing record lists the open leaves of
that revision; a reasoner call that disposes a leaf or closes the session
is refused; and a reopened session keeps its history. This ADR records the
decision, not a completed runtime test.
