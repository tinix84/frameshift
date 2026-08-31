# ADR-0012: Provenance cites a typed, open namespace

- Status: accepted
- Date: 2026-08-31
- Deciders: initial maintainers
- Supersedes: none

## Context

Every proposal, node, and note in FrameShift carries `provenance.source_ids`. It is the field that makes a reasoning case auditable: it is how a claim points at what it came from. Nothing said what it may point at.

The committed reference session cites four values, and they do not agree with each other about where a source lives:

| `source_id` | Resolves to |
|---|---|
| `stmt_001` | a statement in canonical state |
| `node_factor_001` | a graph node in canonical state |
| `intake_001` | an intake record — not in canonical state |
| `art_evidence_001` | a checkpoint artifact — in the envelope, not the state |

So provenance already pointed outside the session, in two different directions, in the one artifact the whole corpus is measured against. When the session invariants landed (#111) they resolved edge endpoints, `active_frame_id`, and approval targets, and deliberately left `source_ids` alone with a comment saying why — honest, but it left the most load-bearing reference in the model unconstrained. "Cites something" is not the same as "cites something that exists".

Three of the four available answers force a change somewhere else: requiring session-local resolution makes the reference session wrong and promotes intake records to first-class state; resolving against the envelope covers the artifact but not the intake record; leaving it unconstrained makes the gap permanent.

## Decision

**A `source_id` carries a type prefix, and the prefix declares which namespace it belongs to.** The registry of prefixes lives in `CONTEXT.md` alongside the vocabulary it names.

**The namespace decides whether the reference must resolve.** A prefix whose namespace is inside canonical state must name something that exists there; a dangling one is an `invariant_violation`. A prefix whose namespace is outside canonical state — an intake record, a checkpoint artifact — is accepted without resolution, because the session genuinely cannot see it.

**The namespace is open, and the prefix set is not.** New namespaces are added to the registry deliberately. A `source_id` carrying no known prefix is a violation: an unrecognised prefix means either a typo or a namespace nobody declared, and both should fail loudly rather than be waved through as "probably external". This is what keeps the openness from becoming an escape hatch that swallows every dangling reference.

## Consequences

Provenance becomes checkable without becoming closed. A claim citing `stmt_999` fails because statements are session-local and there is no such statement; a claim citing `intake_001` passes because intake records are outside the session by construction; a claim citing `xyz_001` fails because no namespace called `xyz` was ever declared.

The registry becomes a real contract. Adding a namespace is an edit to `CONTEXT.md`, which means it is reviewed, and the checker reads the registry rather than restating it.

This ADR does not decide how an external reference is *verified*. An intake record and a checkpoint artifact are accepted here on the strength of their prefix alone. Verifying that `art_evidence_001` names a real artifact requires the checkpoint envelope, which canonical state does not have and should not need; that belongs with the restore path.

Identifier prefixes are now load-bearing in a way they were not. Renaming a prefix is a migration, not a cosmetic change.

## Alternatives considered

- **Session-local only.** Strictest, and the easiest thing to check. Rejected because the reference session becomes wrong: `intake_001` and `art_evidence_001` would have to be promoted into canonical state, which puts the raw intake record inside the digest and makes state grow with material the reasoning does not use.
- **Session plus checkpoint envelope.** Covers `art_evidence_001` but not `intake_001`, and changes what "canonical state is internally consistent" means — the session invariants would need the envelope handed to them, so a session could no longer be validated on its own.
- **Unconstrained by design, provenance as citation.** Honest about the current state and costs nothing, but leaves the field that makes a case auditable as the one field nothing checks.

## Validation

`evals/checks/session.py` resolves every `source_id` whose prefix names a session-local namespace and accepts every one whose prefix names an external namespace. Fixtures cover a dangling session-local reference, an accepted external reference, and an undeclared prefix. The prefix registry in the checker is asserted against `CONTEXT.md`, so the two cannot drift.
