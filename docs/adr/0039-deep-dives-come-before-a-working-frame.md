# ADR-0039: A session opens on the person's question; highlights and deep dives come before a working frame, which only the decision path requires

- Status: accepted
- Date: 2026-11-11
- Deciders: repository owner, through the design grilling of 2026-11-11 on the source-page vision, recorded in [#302](https://github.com/tinix84/frameshift/issues/302)
- Supersedes: ADR-0010 in part, its rule that causal reasoning needs an approved working frame; builds on ADR-0024, ADR-0037 and ADR-0038

## Context

ADR-0010 binds the order of the four engines: a session cannot reach causal
reasoning without an approved working frame. ADR-0024 lets the person
select a frame only from two to five distinct candidates. Both rules
protect a decision from a problem that was framed too early or too
narrowly.

A person who reads a transcript has no competing frames. They have a
question. If the frame gate came first, they would write filler candidates
to reach the text they came to study. A person with a failure report is in
the same position at the start: they must understand the report before
they can frame the problem well.

## Decision

**A session opens on the person's question.** The person states in one
sentence what they want to understand. It is an `observed` statement with
the role `question`, recorded through the person's boundary (ADR-0028).

**The question bounds each deep dive.** A reasoner that answers a highlight
(ADR-0037) receives the question with it.

**Graph nodes and edges can be recorded before a working frame exists.**
Every other rule on nodes and edges stays: who can record what status
(#254, #259), how a provenance kind is earned (ADR-0026), and that `causes`
is reserved for a supported causal assertion.

**The frame gate guards the decision path.** The `frame_selection` gate
keeps the two-to-five rule of ADR-0024 unchanged. An approved working frame
is required before solution generation and before decision and validation.
ADR-0010's order still binds from framing onward on that path.

**A session without a working frame can end only in understanding**
(ADR-0038).

**Four engines stay four.** A deep dive is causal reasoning under the
person's question. It is not a fifth engine.

## Consequences

The person reaches the text first. Framing happens when the person knows
enough to frame, and it uses what the deep dives found.

A session can hold a causal model that no frame bounds. The question is a
weaker boundary than a frame: it has no system boundary and no success
measures. A node recorded under the question can fall outside the frame
that the person later selects. Nothing removes it. The person parks it or
leaves it.

A solution in disguise can enter through a highlight and be analysed
before it is reframed. The decision path still catches it, because no
option and no decision record exists without an approved working frame.

## Alternatives considered

- **Keep framing first for every session.** The rule is simple. But the
  person writes filler frames to reach the page, and the gate teaches them
  that frames are a formality.
- **The question as a frame, selected alone.** It reuses the gate. But it
  breaks the two-to-five rule for all sessions, or needs an exception that
  ADR-0024 would have to carry.
- **No opening question.** It is one step less. But a deep dive then has no
  boundary at all, and a reasoner cannot tell what is in scope.

## Validation

[#298](https://github.com/tinix84/frameshift/issues/298) owns the
implementation and its evidence: a session with a question and no working
frame accepts nodes and edges; it refuses an option and a decision record;
a session that later selects a frame keeps the earlier nodes; and a fixture
covers both paths. This ADR records the decision, not a completed runtime
test.
