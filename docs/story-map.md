# FrameShift story map

The long-term view: who needs what outcome, in what order. This is the North
Star and the shape of the journey toward it — nothing else.

## Rules of this file

Four rules. A change that breaks one of them does not belong here.

1. **Solution-neutral.** No component, topology, vendor, format, or protocol.
   A line that names a mechanism is a solution in disguise; the outcome it
   serves belongs here and the mechanism belongs in [`docs/adr/`](adr).
2. **No status.** Nothing here is "done", "planned", or "in progress". Status
   lives in the issue tracker and nowhere else.
3. **Survives the swap test.** Rewrite every ADR to choose the opposite option.
   If a line in this file changes, that line is duplicating an ADR — cut it.
4. **No stories.** Stories are issues. This file names the columns and the
   slices they sit in; the grid itself is generated from the tracker.

## North Star

> A reasoner who arrives with a solution in disguise leaves with a problem they
> can defend and a decision they can sign — and often enough, neither is the one
> they walked in with.

Two measures, both readable from approved state:

- **Reframe rate** — the share of sessions whose approved working frame differs
  materially from the request that arrived.
- **Decision durability** — the share of signed decisions whose revisit
  triggers never fire.

A release that moves neither measure did not move the North Star.

## Who this is for

**The lone reasoner.** An engineer or technical strategist who arrives with a
fuzzy, half-formed problem and supplies the domain knowledge no model can
infer. Nobody else is in the session.

The accountable decision-owner, the collaborating team, and the integrator are
real and secondary. They hang off this backbone; they do not define it.

## The backbone

The journey, left to right, in the order the reasoner walks it.

| # | Column | The reasoner's outcome |
|---|---|---|
| 1 | Bring a request | Says what they want in their own words, without first having to know what they actually need |
| 2 | Get reframed | Is shown the outcome their request omitted, and chooses the problem they will actually solve |
| 3 | Understand what causes it | Sees why the problem happens, with competing explanations kept side by side rather than collapsed |
| 4 | Find what would tell us | Learns which single observation would separate the explanations, and what it would cost to get |
| 5 | Generate options | Gets candidate interventions that attack the problem at more than one level, including doing nothing |
| 6 | Compare against what matters | Judges options against criteria they own, not against a number someone else computed |
| 7 | Sign the decision | Commits to one option with the rationale, the dissent, and the conditions attached |
| 8 | Carry it onward | Picks the work up somewhere else, later, without losing what was established |
| 9 | Keep what was learned | Promotes what proved reusable, deliberately, and leaves the rest behind |

A request that fits no column is the signal, not an inconvenience: either it is
off the North Star, or the backbone has a hole. Adding a column is a deliberate
act, not a reflex.

## Slices

Each slice is a **thin path across every column** — crude everywhere, missing
nowhere. Depth arrives in later slices, never a column at a time.

| Slice | The reasoner can… |
|---|---|
| 1 | Bring one request, accept one reframe, and sign one decision — shallow at every step, but nothing skipped |
| 2 | Argue about causes: hold competing explanations and be told which observation would separate them |
| 3 | Weigh real alternatives against criteria they own, including the option of not acting |
| 4 | Do all of it with someone else, across sessions and tools |

Slice 1 is the walking skeleton. Until it exists, no exemplar can pass.

## Exemplars

Named cases that cut across the whole backbone. Each has a runnable twin the
evaluation harness executes — an exemplar nobody can execute is an anecdote.
Where the twin lives is the harness's decision, not this file's.

| Exemplar | The reasoner arrives with |
|---|---|
| `battery-single-source` | A margin problem stated as a component cost, where the real exposure is a sourcing position |
| `kafka-in-disguise` | A named technology and no stated outcome at all |

## How this connects to the tracker

This file is the durable half. The grid is the volatile half and is generated,
never copied.

- A `story` label marks an issue as user-facing. Infrastructure issues carry no
  story label and are out of scope here.
- A `column:<name>` label places a story on the backbone.
- The milestone places it in a slice.
- Every `story` issue has exactly one of each.

Written like this — actor, outcome, and why, with no mechanism anywhere:

> As an engineer handed "we need Kafka", I want to be shown the outcome my
> request omits, so that I can push back with something concrete.
