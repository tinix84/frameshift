# ADR-0035: The person authors the deciding words at frame selection and decision approval

- Status: accepted
- Date: 2026-11-07
- Deciders: repository owner, through the design grilling of 2026-11-06 on the companion vision, which feeds [#195](https://github.com/tinix84/frameshift/issues/195) and [#188](https://github.com/tinix84/frameshift/issues/188)
- Supersedes: none; extends ADR-0002 and ADR-0028; ADR-0024's adoption of pre-filled proposals does not apply to the two rationales it names

## Context

A model drafts frames, causes and options faster than a person can read
them. A person who works on several problems at once then approves what
they did not rebuild in their own head. The North Star asks for "a problem
they can defend". A problem that the person cannot explain without the tool
is not defended.

The gates of ADR-0002 bind authority. An approval names a disposition, a
target digest, a revision and an actor. It does not show that the person
understood the target. A disposition takes one click, and a rubber-stamp
passes every gate.

The approval record already has an optional `rationale` of up to 3000
characters. Only the boundary that speaks for the person records an approval
(ADR-0022, ADR-0034). So a rationale on an approval is the person's words by
construction, if no reasoner text fills it first. ADR-0024 lets a person
adopt a proposal pre-filled from the reasoner's text. That is the easiest
path to approve words that are not the person's.

Two gates decide the most: `frame_selection` decides which problem the person
solves, and `decision_approval` decides what the person does about it. Hard
rules at every gate would be a cost that a person with several sessions open
learns to bypass.

## Decision

**Two gates require the person's rationale.** An approval at the
`frame_selection` gate or the `decision_approval` gate, with the disposition
`approved` or `edited`, must carry a `rationale` that is not empty after
trimming. If it does not, the command is refused with `invariant_violation`,
and nothing is written.

- At `frame_selection`, the rationale says why this frame and what the other
  candidate frames miss.
- At `decision_approval`, the rationale is the decision's rationale in the
  person's words.

The other gates, and the other dispositions at these two gates, keep an
optional rationale.

**No reasoner text fills the rationale.** The confirmation for these two
gates shows an empty rationale field. It is never pre-filled from a
reasoner's proposal or rationale summary. If the reasoner supplied rationale
summaries, the person's boundary may show them beside the field, labelled as
the reasoner's. The person does not have to use them. ADR-0024's pre-filled
adoption stays as it is for frames and rungs.

**The rule is a precondition on the command.** It is not a replay invariant.
A history that passed these gates without a rationale, the reference history
included, still folds.

**Only the person stops or resumes exploration.** A phase advances only
through a gate (ADR-0002). Only the person parks or reopens a line
(ADR-0032). A reasoner may propose to stop, with a reason, as a proposal like
any other. A stopping rule can be the reason in such a proposal. It is never
an authority. No reasoner-facing boundary exposes a command that ends a
phase, parks a line or closes exploration.

**The tandem run is the working lane.** In a tandem run (ADR-0034) the person
writes their own attempt in the GUI first, then asks the reasoner. The system
does not enforce this order. ADR-0036 makes the order visible.

## Consequences

The two texts that matter most in a signed decision are the person's own,
and the log proves it. A reader of the log sees why the person chose the
frame and the option, in the person's words.

Each of the two gates costs the person one or two sentences. The other gates
cost nothing more.

The reasoner can still help. Its summary sits beside the field, but it
cannot become the rationale without the person typing it.

The rule does not prove understanding. A person can type a short, empty
reason. [#188](https://github.com/tinix84/frameshift/issues/188) measures
understanding outside the log, with a delayed explain-back. This ADR makes
only the authorship of the deciding words provable.

## Alternatives considered

- **A rationale at every gate.** It makes the cost too high, and a person with
  several sessions open learns to type filler.
- **A reasoner drafts the rationale and the person edits it.** It is fast, but
  the approved words then start as the reasoner's, which is the anchoring this
  ADR exists to stop.
- **A required "first guess" before the candidate frames are shown.** It is
  the strongest stop on anchoring. But it blocks a person who cannot frame the
  request yet. ADR-0036 keeps it as an attempt the person may skip.
- **No rule, and leave understanding to the person.** It keeps the current
  state, where nothing separates a considered approval from a click.

## Validation

[#293](https://github.com/tinix84/frameshift/issues/293) owns the
implementation and its evidence: a `frame_selection` or `decision_approval`
approval without a rationale is refused with an unchanged log; the other gates
and dispositions accept an approval without one; the confirmation shows an
empty field and labels any reasoner summary; the reasoner tool list does not
change; and the reference history still folds. This ADR records the decision,
not a completed runtime test.
