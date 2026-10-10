# ADR-0028: A person's words enter through an intake record minted at their boundary

- Status: accepted
- Date: 2026-10-10
- Deciders: repository owner, through the design decision on #256
- Supersedes: none; extends ADR-0026 and amends its espresso validation

## Context

ADR-0026 lets a node earn the provenance kind `observed` by citing an intake
record or a statement whose own kind is `observed`. That only means "the
person's own words" if `observed` statements really are the person's.

They are not today. `add_statement` gives every statement it records the kind
`observed`, whichever boundary called it. A reasoner could add a statement and
cite it to earn `observed` (#256). The coordinator has no actor to ask: no
statement records who wrote it (#230).

## Decision

**A statement is `observed` only if it cites an intake record minted by the
boundary that speaks for the person.** Two commands record statements:

- **The person's path.** `add_operator_statement` records the text typed by the
  operator as it arrived. It mints a new intake record id (`intake_` prefix,
  ADR-0012) and records the statement with kind `observed`, citing that id.
  This is what `open_session` already does for the request. Only a boundary
  that speaks for the person calls it:
  - the manual GUI, under ADR-0022's operator attestation;
  - later, the trusted-confirmation path.

  A reasoner-facing boundary, such as MCP tools, never exposes it.
- **The reasoner's path.** `add_statement` never records `observed`. A caller
  may declare a provenance with kind `inferred`, `sourced`, `assumed` or
  `unknown`. The sources must earn the kind under ADR-0026's table, and must
  satisfy ADR-0012 on commit. A declared `observed` is refused with
  `invariant_violation`. Without a declared provenance the statement is
  `assumed`.

A reasoner cannot make its own text `observed` by citing someone else's intake
record either. `observed` on a statement asserts that this text is the
person's words, and only the boundary that received them can say so. This is
stricter than ADR-0026's table for nodes, which lets a node earn `observed` by
citing an `observed` statement: a node is a claim *about* the person's words, a
statement claims to *be* them.

**An intake citation names a record that exists.** `intake_` lives outside
canonical state (ADR-0012), so its prefix alone would let a reasoner cite a
record nobody received. A reasoner's citation of an `intake_` id is therefore
accepted only when that id is an intake record minted in this session: one
cited by an `observed` statement. Every refused citation is refused with
`invariant_violation`, before anything is written: an unregistered prefix, a
session-local id that does not resolve, or an unknown intake record.

## Consequences

ADR-0026's `observed` rule can now hold for nodes, so #257 can proceed, on two
conditions this decision sets for it:

- an `intake_` citation earns `observed` only if it names an intake record
  minted in the session, as above;
- a `stmt_` citation earns `observed` only if that statement is `observed`
  *and* cites such an intake record. Sessions recorded before this decision
  hold reasoner statements marked `observed` with no source (the note "Added by
  the reasoner during intake."). Replay and migration keep their provenance as
  it was, so without this condition they would still earn `observed`.

Which commands a boundary exposes now carries authority, not just convenience.
The MCP domain-command server (#172) must not expose `add_operator_statement`.

A reasoner's statement that restates something the person said is recorded as
`inferred` from the person's statement, which is what it is. The espresso
simulation plays the reasoner, so its `observed` statements come out `assumed`
there. Only the person, typing them in the GUI, reproduces them as `observed`.

**This amends ADR-0026's validation.** ADR-0026 expected the espresso `compare`
to show no node-provenance difference after #257. Ten reference nodes are
`observed` and cite only reference statements that the simulation now records
as `assumed`, so the simulation cannot earn `observed` for them. After #257 the
expected result is no node-provenance difference except on those ten. The
reference's own `observed` statements cite no intake record. It is a
hand-authored corpus case, not a recorded session, and that mismatch is
accepted rather than rewriting the case.

Ladder rungs still store a declared provenance unchecked (ADR-0024), including
a declared `observed`. ADR-0026 deferred them, and so does this decision.

## Alternatives considered

- **An actor field on every statement**, derived at the boundary. Closer to
  #230, but it changes the statement schema and both reducers to answer a
  question that the intake namespace already answers.
- **Only the original request is ever `observed`.** Simplest, but the person's
  later answers typed in the GUI would lose their basis, and with them the
  IS / IS NOT observations that ADR-0027 builds on.

## Validation

#256:

- the person's path records `observed` with a fresh `intake_` source;
- the reasoner's path refuses `observed`, defaults to `assumed`, and stores a
  declared `inferred`, `sourced` or `unknown` provenance that its sources earn;
- an unearned, dangling, unregistered or unknown-intake citation is refused
  with `invariant_violation`, and nothing is written;
- the GUI's statement route records the person's path, whatever provenance the
  client sends;
- no reasoner-facing boundary names `add_operator_statement`.
