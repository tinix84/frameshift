# ADR-0025: Migration resets every decided status, not only frames

- Status: accepted
- Date: 2026-10-10
- Deciders: repository owner, through the design decision on #262
- Supersedes: none; extends ADR-0020

## Context

ADR-0020 makes a linked session start without approval authority: converted
frames become `proposed`, and no approval records are copied. The migration
code does exactly that and nothing more. Statements, graph nodes, graph edges
and options are deep-copied with whatever status they had. A source session can
therefore hand the linked session an `approved` node, a `superseded` statement
or a `selected` option with no approval record behind it. That is the pattern
#254 closed for `add_node`: a status that records a decision, held by no one.

## Decision

**A decided status needs its decision, so migration resets it.** In the linked
session, every statement, graph node, graph edge and option whose status records
a decision becomes `proposed`. The decided statuses are `approved`, `rejected`,
`superseded` and `archived`, plus an option's `shortlisted` and `selected`.
`draft` and `proposed` are kept. Frames follow ADR-0020 unchanged. Criteria
carry no status and are copied as they are.

The session's own status is a decision too: a `decided` or `archived` source
session yields a linked session whose status is `active`.

Ids, text, provenance, links and every other field are kept. Only status
changes, and the immutable source checkpoint remains the record of what was
decided before.

## Consequences

The linked session asks again for every decision the source session recorded.
A superseded statement and its correction are both live again. That is the
cost of carrying no authority, and it is the same cost ADR-0020 already
accepted for frames.

**For most items there is no way yet to decide again.** No command emits
`statement.status.changed` or changes a node, edge or option status, and the
linked session starts in framing, past intake. So until the commands that
carry those decisions exist, a reset decision stays unmade:

- superseding a statement (#255);
- withdrawing a frame (#246);
- graph editing (#9);
- option assessment (#12, #13).

This ADR accepts that gap rather than carrying authority across without its
record.

Derived checks that read live statements (for example `abstraction_required`)
can give a different answer on the linked session than on its source, until
the person repeats the decisions.

## Alternatives considered

- **Reset only `approved`, keep withdrawals as history.** Smaller, but a
  rejection or a supersession is also a decision. Kept without its record, it
  would silently shape what the linked session treats as live.
- **Refuse the migration and list the decided items for review.** This reuses
  the existing pending-human-review result. Rejected as the default because it
  blocks every routine history. A person who wants that review gets it anyway,
  because every reset item is `proposed` again.

## Validation

#262: a fixture whose source holds an approved node, a superseded statement, a
selected option and a `decided` session migrates the first three to `proposed`
and the session to `active`, with every other field unchanged. The linked
session holds no decided status lacking an approval record in that session.
