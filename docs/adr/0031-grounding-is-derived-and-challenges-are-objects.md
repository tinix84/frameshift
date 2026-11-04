# ADR-0031: A node's grounding is derived from what it rests on; a challenge is a session object

- Status: accepted
- Date: 2026-11-04
- Deciders: repository owner, through the design grilling on #90 and #92
- Supersedes: none; extends ADR-0003 and ADR-0026

## Context

Every graph node and edge carries a provenance kind (ADR-0026). A node can
therefore say whether it is observed, sourced, inferred, assumed or unknown.
Nothing tells the person how much of a deep chain rests on fact and how much
rests on opinion.

The person needs that answer for two acts:

- to judge a hypothesis that sits several inferences away from the evidence;
- to choose where to restart when a line of reasoning fails (#90, #92,
  ADR-0032). The best restart point is the most solid part of the graph.

A doubt about a node also has no home today. A `contradicts` edge needs a
counter-node. A doubt often has no counter-node yet, and it needs an answer.

Two rules limit any measure. A score is never a fact (CONTEXT.md). A number
needs a calibrated method (confidence band). #60 asks whether a derived
score may drive behavior.

## Decision

**Each provenance kind maps to one grounding class.**

| Provenance kind | Grounding class |
|---|---|
| `observed`, `sourced` | fact |
| `inferred` | inference |
| `assumed` | opinion |
| `unknown` | gap |

**A node's ground set is the distinct bases it rests on.** The walk starts
at the node and moves backward along live support edges. It continues
through `inferred` nodes and stops at every other node. Each node where it
stops is a base. Each base counts once, however many paths reach it. A
cycle cannot loop, because the walk visits each node once. An `inferred`
node that no support edge reaches is a base of class inference.

Support edges, and the node that rests on the other:

| Edge | The node that rests |
|---|---|
| `supports`, `causes`, `contributes_to` | the target rests on the source |
| `tests`, from an `evidence` node only | the target rests on the source |
| `derived_from` | the source rests on the target |

`enables`, `requires` and every other edge type carry no support. A live
edge or node has the status `draft`, `proposed` or `approved`. The walk
does not follow an edge that is not live. It stops at a node that is not
live, and that base is broken ground.

**A challenge is a session object.** A challenge (`chal_`) names one target,
a graph node or a graph edge. It carries the objection text, the actor who
raised it, and a status: `open`, `answered` or `conceded`. Three events
record it: `challenge.raised`, `challenge.answered` and `challenge.conceded`.
Both reducers fold them, under ADR-0013's lockstep.

- Any boundary may raise a challenge, a reasoner-facing boundary included.
  Doubt decides nothing.
- Only the boundary that speaks for the person answers or concedes one. The
  MCP domain-command server (#172) never exposes these two commands.
- An answer cites one or more source ids (ADR-0012), and each must resolve.
  The answer is as strong as the weakest class it cites. An answer that cites
  only facts is "answered by fact". Any other answer is "answered by opinion".
- A conceded challenge changes no status. It stays on the target as a known
  weakness until the person revises or rejects the target.
- A live `contradicts` edge counts as an open challenge on its target. Its
  objection is the source node.

**The grounding profile shows the strength of a node.** It holds:

- the bases by class: fact, inference, opinion and gap;
- the bases that are not yet decided (`draft` or `proposed`);
- the broken bases, and the parked bases (ADR-0032);
- the challenges on the node: open, answered by fact, answered by opinion,
  and conceded;
- the open challenges upstream, on any node or edge the walk crossed;
- the weakest base: a broken base first, then gap, opinion, inference and
  fact, with ties broken by id order.

**The grounding band colours a node.**

- **weak**: a base is broken, or the node itself has an open or conceded
  challenge, or no base is a fact.
- **solid**: every base is a fact, no challenge is open on the node or
  upstream, and no base is broken or parked.
- **mixed**: every other node.

A solid node that no other solid node rests on is solid ground. Solid ground
is the suggested anchor for a restart (ADR-0032).

**Grounding is derived on read.** The profile, the band and solid ground are
derived from state, as `derived.frame_set` is. No event records them, and
the state digest never covers them. They never change a status. They never
refuse a command or a gate. They order and highlight only.

**The confirmation request shows the grounding.** When a gate targets graph
items, the confirmation request shows each target's grounding profile. The
person still decides.

**New events name their actor.** Each challenge event carries an `actor`
(`common.schema.json`). In single-operator mode the actor is the operator.
#230 owns the actor on earlier event types.

## Consequences

The person can see, on each node, how much rests on fact. A rejected base
shows every node built on it as broken ground. That shows where a line
failed and where a restart can start.

A reasoner gets a bounded task: raise the strongest challenges to a node. The
person keeps the judgement, because only the person closes a challenge.

#60 is settled for grounding: a derived measure may order and inform, and it
never gates. #65 can use the grounding profile as an input to its promotion
rule for `causes`.

The work needs a challenge schema, three event types, a fixture folded by
both reducers, source-id resolution for answers, and the derivation.

## Alternatives considered

- **One ratio of facts to all bases.** Easy to read, but ten facts and one
  load-bearing assumption read as 91 % solid. The profile names the weakest
  base instead.
- **Count every path.** One reused fact then counts many times, and a cycle
  never ends.
- **Record the strength on the node.** It goes stale whenever any upstream
  node changes.
- **Let the band gate a command.** It puts a formula in place of the
  person's judgement.
- **Use only `contradicts` edges for doubt.** A doubt often has no
  counter-node, and an edge has no answer.
- **Free-text answers.** A plain "no" would close any challenge.
- **Let a reasoner close a challenge.** Closing is a judgement, and only the
  person decides (#254).
- **Also walk the source ids in provenance.** It mixes two structures. The
  edges are the graph's own statement of what rests on what.

## Validation

The implementation issues cut from #90 and #92:

- a fixture where two paths reach one fact counts that fact once;
- a cycle of `inferred` nodes ends, and it has no fact base, so it is weak;
- a rejected base makes every node that rests on it weak, with the base
  named as broken;
- `enables` and `requires` edges add no base;
- a `contradicts` edge counts as an open challenge on its target;
- an open challenge on a support edge shows as upstream on every node above it;
- an answer that cites an `assumed` node is "answered by opinion";
- an answer with a source id that does not resolve is refused, and nothing is
  written;
- a reasoner-facing boundary raises a challenge, and it cannot answer or
  concede one;
- deriving the profile leaves the state digest unchanged;
- the battery walkthrough graph gives a band for each of its 36 nodes.
