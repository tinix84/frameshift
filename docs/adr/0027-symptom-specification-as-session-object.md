# ADR-0027: The IS / IS NOT symptom specification is a session object

- Status: accepted
- Date: 2026-10-10
- Deciders: repository owner, through the design decision on #260
- Supersedes: none

## Context

The espresso corpus case (#251) specifies the symptom before analysing it. A
vague complaint is split into deviations, and each deviation is described across
four dimensions (what, where, when, extent), each with an IS and an IS NOT: the
closest case where the deviation does not occur. The contrasts, not the list of
causes, decide which part of the cause tree is worth analysing.

No canonical field holds this. The reference keeps it in
`extensions.symptom_specification`. No command writes session extensions, so a
session built through the application carries none of it (#252, #260).

## Decision

**A session holds a list of symptom specifications, written by a command.**
Session v2 gains an optional `symptom_specifications` list. Absent means none,
so existing v2 sessions and checkpoints stay valid. Each specification has:

- an id with the prefix `spec_`, registered in the `CONTEXT.md` namespace table
  as living in canonical state;
- `object` and `deviation`: one object and one deviation per specification;
- `rows`: up to four, at most one per `dimension` (`what`, `where`, `when`,
  `extent`). A specification may be partial; the reference's second deviation
  has three rows. Each row holds:
  - `dimension`;
  - `is` and `is_not`: lists of statement ids;
  - `distinction`: text;
  - optionally, `needs_more_data`: a boolean.
- optionally:
  - `reference`: a `measure`, its `expected` value, and `source_ids`;
  - `actual`: a `value` and `source_ids`;
  - `knot_node_id`: the graph node the deviation becomes;
  - `method_source_ids`: the method the specification follows, as `art_` ids;
  - `provenance`, under ADR-0012 and ADR-0026.

**Integrity at record time.**

- Every statement id in a row, and every `stmt_` id in a citation, must resolve
  to a statement in the session, whatever its status. A superseded statement
  can still be the IS NOT that matters.
- A `knot_node_id`, when given, must resolve to an existing node. A
  specification recorded before the graph exists omits it, and gains it when
  recorded again in causal.
- A dangling id is refused with `invariant_violation`, and nothing is written.

The command `record_symptom_specification` records a specification, or, given
its id, records it again whole, like a ladder rung (ADR-0024). It emits
`symptom.specification.recorded`, and the earlier recording stays in the
history. It is accepted in intake, framing and causal. A specification belongs
before causal branching, but its knot node exists only once the graph does.

Bibliographic citations stay `art_` references (ADR-0012), with their records
carried by checkpoint artifacts. `views` and `corpus` stay extensions: they are
presentation and fixture metadata, not reasoning state. So do the reference's
collection-level `status` and `note`, which describe the corpus case, not a
specification.

**This narrows #260.** #260 asked for the specification *and the citations* to
be reproduced. Citation records are not session state under this decision, so
`compare` will report the reference's `extensions.citations` as an extension
the application does not hold. That is by design, not a gap. The citations stay
reachable through the `art_` ids the specification and the graph carry.

## Consequences

The reasoning that pruned the cause tree becomes state the application
validates, replays and shows, instead of an extension it cannot see.

The lockstep cost follows ADR-0013 and ADR-0024:

- the v2 session schema;
- both reducers;
- the `CONTEXT.md` prefix registry and its mirror in the evaluation harness;
- `CONTEXT.md` vocabulary for *symptom specification*, *deviation* and *knot
  node* (AGENTS.md working method 9);
- a v2 history fixture.

No gate requires a specification yet. Whether `frame_selection` should expect
one for an observation-led request is a separate decision.

## Alternatives considered

- **Tags on statements** (a dimension, plus an IS or IS NOT flag, grouped by
  deviation). Lighter, but the distinction, the reference and the link to the
  knot node have nowhere to live.
- **Stay an extension, with a command to write extensions.** Cheapest, but the
  specification stays outside the contract, so nothing validates its citations
  or replays it.

## Validation

#260 (as narrowed above):

- a schema and reducer change with a v2 history fixture;
- the command records and re-records a specification;
- a dangling statement or node id is refused, and the refused write leaves
  nothing;
- an existing v2 checkpoint without the field still validates;
- after the change, the espresso `compare` reports both specifications as
  reproduced, including the three-row one. The reference keeps
  `method_source_ids` on the whole list; the simulation carries it onto each
  specification, which is where this decision puts it.
