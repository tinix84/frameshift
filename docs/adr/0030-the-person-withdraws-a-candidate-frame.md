# ADR-0030: The person withdraws a candidate frame, by `frame.status.changed`

- Status: accepted
- Date: 2026-10-14
- Deciders: repository owner, through the design decision on #246
- Supersedes: none; extends ADR-0024 and ADR-0029

## Context

ADR-0024 refuses `frame_selection` unless the session holds two to five live,
mutually distinct candidate frames. No command changes a frame's status, so a
session that reaches six candidates, or holds two frames that agree on outcome,
abstraction level and system boundary, can never leave framing (#246). The
manual GUI guards against it before a frame is proposed; an API client has no
such guard. ADR-0025 also leaves a migrated session unable to decide again on
its frames until a frame can be withdrawn.

A withdrawn frame is `rejected`, a decided status (ADR-0025), and only the
person decides (#254).

## Decision

**A frame's status changes by `frame.status.changed`.** The event carries the
frame's `id` and its new `status`, mirroring `statement.status.changed`. Both
reducers fold it in place, under ADR-0013's lockstep. Withdrawal sets
`rejected`; a later status move reuses the event without another vocabulary
change.

**The person withdraws a candidate.** `withdraw_frame` is a command for the
boundary that speaks for the person, like `supersede_statement` (ADR-0029):

- the manual GUI calls it, under the operator attestation (ADR-0022);
- a reasoner-facing boundary, such as MCP tools, never exposes it.

It is accepted in framing. One commit carries the status change and the
frame's digest, re-recorded with its new status, so a digest is never stale
(ADR-0024). The frame keeps its id and every other field. It is refused with
`invariant_violation`, and nothing is written, when:

- the frame does not exist;
- the frame is the working frame: the person activates another candidate
  first, so `active_frame_id` never names a withdrawn frame;
- the frame is not live (already `rejected`, `superseded` or `archived`).

**Withdrawal is final, and carries no reason.** A withdrawn frame cannot be
activated again: `activate_frame` refuses a frame that is not live. To bring
its content back, the person proposes it again as a new candidate. No gate
binds a withdrawn frame: `frame_selection` approves the working frame only,
and the working frame is never withdrawn. Final holds within a session; a
linked session made by migration resets every decided status to `proposed`
(ADR-0025), as it does for every other decision. Like a
supersession (ADR-0029), withdrawal records no actor; that belongs to #230.

**A withdrawn frame no longer counts.** `derived.frame_set` already reads live
frames only (ADR-0024), so withdrawing one candidate from six, or one of two
twins, makes `frame_selection` reachable again.

## Consequences

`frame_selection` can no longer be made unreachable by proposing too many
frames or a twin: the person withdraws one in the GUI. An API client still
cannot unblock itself; it waits for the person, which is what a decided status
requires.

`withdraw_frame` joins `add_operator_statement` and `supersede_statement` on
the list the MCP domain-command server (#172) must not expose.

## Alternatives considered

- **A narrow `frame.withdrawn` event.** Clearer in the log, but every later
  frame status move would need its own event type.
- **Withdrawing the working frame clears `active_frame_id`.** One step fewer,
  but the session then has no working frame, and `frame_selection` no target,
  until one is activated.
- **A reason on the event and the frame.** Shown in the record, but it adds a
  schema field and validator work for no rule that reads it.
- **A reasoner withdraws its own candidates.** An API client could unblock a
  dead end itself, but it would set a decided status without the person, which
  #254 and ADR-0025 refuse.

## Validation

#246:

- both reducers fold `frame.status.changed`, with a v2 history fixture folding
  to the same state in both;
- withdrawing a frame removes it from `derived.frame_set`; a session with six
  candidates, or with a twin, withdraws one and then seals `frame_selection`;
- the frame keeps its id and text, and its digest is re-recorded;
- the working frame, a missing frame and a withdrawn frame are refused, with
  nothing written, and a withdrawn frame cannot be activated again;
- `frame_selection` refuses any target but the working frame;
- no reasoner-facing boundary names `withdraw_frame`;
- the manual GUI offers withdrawal on each live candidate that is not working.
