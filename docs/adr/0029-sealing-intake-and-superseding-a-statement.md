# ADR-0029: Sealing intake proposes its statements; the person supersedes a statement by naming its replacement

- Status: accepted
- Date: 2026-10-14
- Deciders: repository owner, through the design decision on #255
- Supersedes: none; extends ADR-0021 and ADR-0025

## Context

Two gaps in statement status, found by the espresso simulation (#255):

- **Sealing intake changes nothing on a statement.** Approving
  `intake_correction` records the approval and moves the phase. Every
  statement stays `draft`, so nothing on a statement shows that intake was
  sealed. The espresso reference marks its statements `proposed` once intake
  is sealed.
- **Nothing supersedes a statement.** The person's first answer can be
  corrected by a later one. The reference keeps both and marks the first
  `superseded`. The application can only keep both as `draft`. Both reducers
  fold `statement.status.changed`, but no command emits it.

ADR-0021 forbids rewriting a statement and rejected supersession as the way to
*correct a classification*. Superseding one statement with another is a
different act: the person says that another statement, in its own words,
replaces this one. Both stay, word for word. Usually the replacement came
later, but the person may also fall back on an earlier one.

ADR-0025 counts `superseded` as a decided status. A decided status needs its
decision, and only the person decides (#254).

## Decision

**Sealing intake proposes every live, classified draft.** When
`intake_correction` is approved, the same commit carries one
`statement.status.changed` to `proposed` for each statement that is `draft` and
has a primary role. A statement without a primary role stays `draft`: past
draft, a statement must be classified (#226). A `rejected`, `superseded` or
`archived` statement keeps its status. The approval binds the content the
person saw; the status change follows it in the commit, so the binding is not
disturbed.

**The person supersedes a statement, naming its replacement.**
`supersede_statement` is a command for the boundary that speaks for the
person, like `add_operator_statement` (ADR-0028):

- the manual GUI calls it, under the operator attestation (ADR-0022);
- a reasoner-facing boundary, such as MCP tools, never exposes it.

It is accepted in intake, framing and causal, where statements are reasoned
over. It emits `statement.status.changed` with status `superseded` and
`superseded_by`, the id of the replacing statement. Both statements keep their
id and text. It is refused with `invariant_violation`, and nothing is written,
when:

- either statement does not exist;
- the replacement is the statement itself;
- either statement is not live (`rejected`, `superseded` or `archived`);
- the statement is unclassified: past draft a statement must be classified
  (#226), so the person classifies it first.

The second rule makes a chain of supersessions impossible to close into a
cycle: a superseded statement can never supersede another.

**The replacement is held on the statement.** A session v2 statement gains an
optional `superseded_by`. Absent means none, so existing sessions and
checkpoints stay valid. Both reducers set it from the event, and both
validators check it word for word:

- `superseded_by` names a statement in the session, never the statement
  itself;
- a statement with `superseded_by` has status `superseded`.

A `superseded` statement without `superseded_by` stays valid: sessions recorded
before this decision have them.

**Migration drops it with the status.** ADR-0025 resets a `superseded`
statement to `proposed` in a linked session. `superseded_by` is part of that
decision, so it is reset with it. Every other field is kept, as ADR-0025 says.
Today's migration converts v1 sources only, and a v1 statement cannot carry
`superseded_by`, so this holds for any later migration rather than changing
one now.

**A superseded statement is not live.** Derived intake checks, such as
`abstraction_required`, already read only live statements, and no gate binds a
withdrawn statement: `intake_correction` neither offers nor accepts one as its
target. A superseded statement keeps its provenance, so an `observed` one is
still the person's words and still earns `observed` (ADR-0026, ADR-0028). Its
classification can still be corrected; that changes no status.

**No actor is recorded.** Like a statement and its classification (ADR-0021),
a supersession records no actor in its event. Its authority is the boundary
that issued it, under the operator attestation, as for
`add_operator_statement`. Recording who decided belongs to #230, which decides
how an actor enters the vocabulary for all of them at once.

## Consequences

The status of a statement now says something: `draft` while intake is open,
`proposed` once it is sealed, `superseded` when the person has replaced it, and
by what.

Which commands a boundary exposes carries authority (ADR-0028), and
`supersede_statement` joins `add_operator_statement` on the list the MCP
domain-command server (#172) must not expose.

The espresso simulation plays the reasoner, so it never supersedes. Its test
supersedes `stmt_espresso_006` by `stmt_espresso_007` as the person, as it seals
the gates. Then `compare` shows no statement-status difference.

## Alternatives considered

- **Statements stay `draft` after sealing.** No events at the gate, but nothing
  on a statement shows intake was sealed, and the espresso reference keeps
  differing on every statement.
- **Supersession through a confirmation gate.** One approval record per
  supersession is the strongest audit, but it adds a gate kind and a dialog for
  every correction of an answer.
- **The replacement only in the event payload.** No schema change, but state
  cannot show what replaced a statement, and no validator can check it.

## Validation

#255:

- sealing intake proposes live classified drafts in the gate's commit, and
  leaves an unclassified draft and a superseded statement as they were;
- the command records `superseded` and `superseded_by`, keeps both statements'
  text and id, and refuses each case above with nothing written;
- both validators agree on `superseded_by`, with a v2 history fixture;
- a v1 source carrying `superseded_by` is refused;
- no gate binds a withdrawn statement, and an unclassified one cannot be
  superseded;
- no reasoner-facing boundary names `supersede_statement`;
- after the change, the espresso `compare` shows no statement-status
  difference.
