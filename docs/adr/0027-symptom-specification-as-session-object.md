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
Session v2 gains `symptom_specifications`. Each specification has:

- an id with the prefix `spec_`, registered in the `CONTEXT.md` namespace table
  as living in canonical state;
- `object` and `deviation`: one object and one deviation per specification;
- `rows`: one per dimension (`what`, `where`, `when`, `extent`). Each row holds
  `is` and `is_not` as lists of statement ids, and `distinction` as text;
- optionally, `reference` (a measure and its expected value, with source ids)
  and `actual` (the observed value, with source ids);
- optionally, `knot_node_id`: the graph node the deviation becomes;
- provenance, under ADR-0012 and ADR-0026.

The command `record_symptom_specification` records a specification, or, given
its id, records it again whole, like a ladder rung (ADR-0024). It emits
`symptom.specification.recorded`, and the earlier recording stays in the
history. It is accepted in intake, framing and causal. A specification belongs
before causal branching, but its knot node exists only once the graph does.

Bibliographic citations stay `art_` references (ADR-0012), with their records
carried by checkpoint artifacts. `views` and `corpus` stay extensions: they are
presentation and fixture metadata, not reasoning state.

## Consequences

The reasoning that pruned the cause tree becomes state the application
validates, replays and shows, instead of an extension it cannot see.

The lockstep cost follows ADR-0013 and ADR-0024:

- the v2 session schema;
- both reducers;
- the `CONTEXT.md` prefix registry and its mirror in the evaluation harness;
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

#260: schema and reducer change with a v2 history fixture; the command records
and re-records a specification, and a refused write leaves nothing. After the
change, the espresso `compare` reports the symptom specification as
reproduced.
