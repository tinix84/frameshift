# ADR-0032: A dead end is a parked line; the person restarts from a node in the same session

- Status: accepted
- Date: 2026-11-04
- Deciders: repository owner, through the design grilling on #90 and #92
- Supersedes: none; extends ADR-0031; leaves ADR-0030 unchanged

## Context

Reasoning about a hard problem goes down lines that fail. The person then
goes back to a sound point and takes another line. On a long problem the
person loses track of where that point was. #90 asks what makes a reasoning
path traceable, reversible and branchable. #92 asks how a stopped line is
represented and reopened without calling its claims false.

Three facts limit the answer:

- Each session has one linear event log (ADR-0013). Every ADR since
  ADR-0004 assumes that one session has one revision sequence.
- ADR-0019 already makes a linked session for migration. It starts a new
  history and carries no authority from its source.
- ADR-0030 makes the withdrawal of a candidate frame final. A dead end that
  can be reopened must therefore be something other than a withdrawal.

ADR-0031 shows how solid each node is. The most solid part of the graph is
the natural point to restart from.

## Decision

**A dead end is a parked line.** A parked line (`line_`) is a set of graph
nodes that the person stops working on. Parking is a disposition about
effort, not a verdict on truth. Every node and edge keeps its status.

**The person names an anchor and one or more tips.** The anchor is the node
the line grows from. The tips are where the line ends. The person's boundary
proposes the nodes of the line, and the person confirms the exact set:

1. Take every node on a live support path (ADR-0031) between the anchor and
   a tip. The tips are in the set. The anchor is not.
2. Remove each node, other than a tip, that a live node outside the set rests
   on. Repeat until no node is removed. A shared node therefore stays live.

The event records the confirmed node ids, not the rule. A reducer never
recomputes the set.

**Two events record a line.** `line.parked` carries the line id, the anchor,
the tips, the node ids, a reason code, a reason text and the actor.
`line.reopened` carries the line id, a reason text and the actor. Both
reducers fold them, under ADR-0013's lockstep. The reason codes come from #92:

| Code | Meaning |
|---|---|
| `insufficient_evidence` | the evidence to go on is not available |
| `low_decision_value` | the result would not change the decision |
| `contradicted` | the line conflicts with stronger ground |
| `duplicate` | another line covers the same ground |
| `out_of_scope` | the line is outside the working frame |

The reason text is one sentence and is required for both events. The reason
is the thread the person reads when they come back.

**A node is parked while a parked line holds it.** A node can be in more than
one line. A reopened line is final. To park the same nodes again, the person
parks a new line, so the log keeps each episode. A node may still gain edges
and challenges while it is parked.

**A parked node is parked ground, never broken ground.** A live node that
rests on a parked node counts that base by its grounding class. Its grounding
profile names the parked base, and it cannot be solid (ADR-0031).

**A restart is a parked line plus new work from its anchor.** The person parks
the failed line. Then the person adds new nodes that rest on the anchor, in
the same session. No new command is needed for the restart itself. The graph
holds the branches, and the log keeps the order in time. The parked line stays
on the canvas, greyed, next to the new line.

**Only the person parks or reopens.** Both commands belong to the boundary
that speaks for the person: the manual GUI, under the operator attestation
(ADR-0022). The MCP domain-command server (#172) never exposes them. A
reasoner may suggest a line to park, or an anchor to restart from. It never
records a park or a reopen.

**Both commands are accepted while the session is active.** They are refused
with `invariant_violation`, and nothing is written, when:

- the anchor, a tip or a listed node does not exist;
- the node set is empty or holds the anchor;
- the reason code is not in the table, or the reason text is empty;
- a reopen names a line that does not exist or is already reopened.

**A fork in time is not decided.** "Go back to revision N" with a new session
is outside this decision. ADR-0019 remains the only way to make a session
from another session. A later ADR decides time forks if the need appears.

**ADR-0030 stays as it is.** Parking applies to graph nodes only. A withdrawn
frame stays withdrawn. To use its content again, the person proposes it as a
new candidate frame.

## Consequences

The person sees each dead end on the same map as the live lines, with the
reason it stopped and who stopped it. The person can reopen a line, and its
claims never lost their status.

The event log stays linear. Revision, digest, gate and checkpoint rules do not
change. The parked lines are canonical state, so the state digest covers them.

The work needs a line schema, two event types, a fixture folded by both
reducers, the proposal of the node set, and the canvas actions.

Frames have no parking. If frame-level dead ends are missed in practice, a
later ADR can add them.

## Alternatives considered

- **Fork into a new linked session from a revision.** It keeps each log
  linear, but it splits the map. The person then needs two canvases to see
  the dead end and the new line.
- **Branch ids inside one session.** One log could hold the tree, but the
  revision, digest, gate and checkpoint rules would all change.
- **A `parked` node status.** It would mix a disposition about effort with
  the decided statuses that only the person sets (ADR-0025).
- **Park everything downstream of the anchor.** One shared node could park
  half the graph without notice.
- **Let a reasoner park a line.** Parking decides where effort goes, so it is
  the person's choice.
- **An optional reason.** A park without a reason loses the thread.
- **Make a withdrawn frame reopenable.** It would supersede ADR-0030 to solve
  a problem that parking already solves on the graph.
- **The term "dead end" or "branch".** "Dead end" sounds final. "Branch"
  collides with git and with the time fork that is not decided.

## Validation

The implementation issues cut from #90 and #92:

- both reducers fold `line.parked` and `line.reopened`, and a history fixture
  folds to the same state in both;
- a park keeps the status of every node and edge in the line;
- the proposed set keeps a shared interior node live, and keeps the tips;
- a park with an unknown code, an empty reason or the anchor in the set is
  refused, and nothing is written;
- a node that rests on a parked node shows parked ground, and it is not solid;
- a second reopen of the same line is refused;
- no reasoner-facing boundary names the park or reopen command;
- the canvas greys a parked line and offers "Park line" and "Reopen".
