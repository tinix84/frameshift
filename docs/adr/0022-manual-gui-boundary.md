# ADR-0022: A local manual GUI as a second inbound boundary

- Status: accepted
- Date: 2026-10-06
- Deciders: repository owner, on review of [#235](https://github.com/tinix84/frameshift/pull/235)
- Supersedes: ADR-0014 in part, its rule that the native Claude Code dialog is the only approval interface, and only for sessions run under the manual-mode attestation below; extends ADR-0015's module table with `gui`

## Context

The walking skeleton ([#89](https://github.com/tinix84/frameshift/issues/89))
is blocked on reasoning-engine behaviour ([#6](https://github.com/tinix84/frameshift/issues/6),
[#7](https://github.com/tinix84/frameshift/issues/7)), which
[#223](https://github.com/tinix84/frameshift/issues/223) names as the likeliest
slip: a prompt-and-eval loop with no crisp definition of done. Orchestration,
the event log, the gates and the confirmation binding do have one, and today
they can only be exercised through test code or through a model.

ADR-0006 makes an engine result a contract, not a provenance claim. A person
can author that contract by hand, and orchestration admits it by the same rules.
That separates two questions the skeleton currently couples: whether the
journey works, and whether a model fills it in well.

ADR-0014 makes Claude Code's native elicitation dialog the first release's only
approval interface. Its threat is a model issuing or rewriting approvals, and
its defence is a dialog the agent cannot answer. A local web page has no such
property: anything running as the operator can request it over loopback, read
the token it embeds, and post a confirmation. Whether a model is connected *to
this process* does not decide that; whether an agent runs *under this account*
does.

## Decision

Add `frameshift.gui`, an inbound boundary peer of `frameshift.mcp`.

| Module | May import |
|---|---|
| `gui` | `contracts`, `orchestration.api` |

`bootstrap` alone assembles it. It serves one static page and JSON routes over
the standard library's HTTP server, bound to the loopback interface. Serving it
beyond loopback is ADR-0023's decision, not this one.

**Manual mode is an operator attestation, not a property the process checks.**
By launching the server the operator attests that no agent or model runs under
their account while it is open. `bootstrap` builds an approval profile for
client `frameshift-manual-gui`, pinned by the digest of a launch configuration
that includes that attestation's text, and an operator attestation naming the
human and role given on the command line. The server prints the attestation at
start and the page states it. This is the same kind of guarantee ADR-0014
already rests on: an operator's assertion about the configuration, not
FrameShift's verification of it.

Every existing guard still decides: the confirmation broker binds the response
to the displayed request digest, target digest, revision and actor authority,
and `transitions.attempt` applies sequence then binding. The GUI adds no
approval logic.

**Every approval names the profile that bound it.** The canonical approval
record carries an optional `profile_id`, an opaque reference to the attested
approval profile, set by the confirmation broker for every interface. Local
and hosted runs of the GUI are distinct profiles. Approvals bound under a
manual-GUI profile are never evidence for ADR-0014's native-dialog guarantee
([#205](https://github.com/tinix84/frameshift/issues/205)), and sessions
carrying them are not model-produced reasoning for engine evaluation. Approvals
recorded before the field existed omit it and remain valid.

The server refuses a `Host` header other than its own loopback address, and
every API call must carry a per-launch token embedded in the page, sent in a
custom header a cross-origin page cannot send without a preflight the server
never answers. That defends against other web origins, not against a local
agent; the attestation covers the local agent.

## Consequences

The journey can be walked, demonstrated and regression-tested without a model,
and engine work can be judged against sessions a person produced by hand.

Two approval interfaces now exist, and the log says which one bound each
approval. A manual-GUI profile must not be reused by a process that also runs
the MCP server or connects a model.

The manual mode's guarantee is exactly as strong as the operator's attestation.
Running the GUI in the same account as Claude Code, Codex or another agent
breaks it silently: the agent can approve, and the log will name the manual
profile and the human operator. Nothing here protects against a compromised
browser, operating system or local user, which ADR-0014 also excludes.

Adding `profile_id` to the approval record is an additive change to
`session.v2`. A reader built on an earlier copy of the schema, which rejects
additional properties, refuses approvals that carry it; within this repository
schema and readers move together.

Columns the event vocabulary cannot yet express — options, criteria, the signed
decision — are absent from the GUI rather than stored outside the log.

## Alternatives considered

- **Proposal-only GUI**, approvals still through Claude Code: keeps ADR-0014
  whole, but the journey then cannot be completed without a model-capable
  client, which is the coupling this decision removes.
- **Scope manual mode to "no model connected to the process"**: the first
  draft of this ADR. It describes something the process can state but not a
  boundary an agent respects, so it overstated the guarantee.
- **Third-party UI framework** (Streamlit, FastAPI and a front-end build): faster
  widgets, but adds runtime dependencies to a repository that runs on the
  standard library, and a second process model to secure.
- **A command-line approval tool**: ADR-0014 rejected it because an agent can
  invoke it. The same holds for a loopback page, which is why this decision
  rests on the attestation rather than on the interface.
- **Record the client id on the approval**: more legible, but puts a client
  name into canonical state, which #205 keeps provider-neutral; the opaque
  profile id resolves to the client through the attested profile.

## Validation

`frameshift/tests/test_sessions.py` and `frameshift/tests/test_gui.py` hold the
evidence: the GUI imports only what the table above permits; forged request
digests, stale content, wrong phase and insufficient role are refused and
append nothing; requests without the token or with a foreign `Host` are refused;
an approval made through the GUI records the local manual profile, local and
hosted runs are distinct profiles, and an approval without `profile_id` still
validates; and a session walked from request to `solutions` folds to a
schema-valid state. The import rule joins the enforcement owned by
[#216](https://github.com/tinix84/frameshift/issues/216).
