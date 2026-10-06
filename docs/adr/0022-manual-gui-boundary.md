# ADR-0022: A local manual GUI as a second inbound boundary

- Status: proposed
- Date: 2026-10-06
- Deciders: repository owner (pending)
- Supersedes: ADR-0014 in part, its rule that the native Claude Code dialog is the only approval interface, and only for sessions run with no model connected; extends ADR-0015's module table with `gui`

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
approval interface. Its threat is a model issuing or rewriting approvals. With
no model connected, that threat has no actor, but the ADR's rule still forbids
a second interface.

## Decision

Add `frameshift.gui`, an inbound boundary peer of `frameshift.mcp`.

| Module | May import |
|---|---|
| `gui` | `contracts`, `orchestration.api` |

`bootstrap` alone assembles it. It serves one static page and JSON routes over
the standard library's HTTP server, bound to the loopback interface.

In **manual mode** — no model, MCP client or agent connected to the process —
the GUI may answer confirmation requests. The operator attests by launching
the server: `bootstrap` builds an approval profile for client
`frameshift-manual-gui`, pinned by the digest of its launch configuration, and
an operator attestation naming the human and role given on the command line.
Every existing guard still decides: the confirmation broker binds the response
to the displayed request digest, target digest, revision and actor authority,
and `transitions.attempt` applies sequence then binding. The GUI adds no
approval logic.

The server refuses a `Host` header other than its own loopback address, and
every API call must carry a per-launch token embedded in the page, sent in a
custom header a cross-origin page cannot send without a preflight the server
never answers.

## Consequences

The journey can be walked, demonstrated and regression-tested without a model,
and engine work can be judged against sessions a person produced by hand.

Two approval interfaces now exist. The manual one is valid only while the
process has no model connected; connecting one, or running the MCP server in
the same process, is outside this decision and must not reuse its profile.
Nothing here protects against a compromised browser, operating system or local
user, which ADR-0014 also excludes.

Columns the event vocabulary cannot yet express — options, criteria, the signed
decision — are absent from the GUI rather than stored outside the log.

## Alternatives considered

- **Proposal-only GUI**, approvals still through Claude Code: keeps ADR-0014
  whole, but the journey then cannot be completed without a model-capable
  client, which is the coupling this decision removes.
- **Third-party UI framework** (Streamlit, FastAPI and a front-end build): faster
  widgets, but adds runtime dependencies to a repository that runs on the
  standard library, and a second process model to secure.
- **A command-line approval tool**: ADR-0014 rejected it because an agent can
  invoke it; that objection holds for a CLI an agent shares a shell with, and
  is the reason this decision is scoped to sessions with no agent present.

## Validation

`frameshift/tests/test_sessions.py` and `frameshift/tests/test_gui.py` hold the
evidence: the GUI imports only what the table above permits; forged request
digests, stale content, wrong phase and insufficient role are refused and
append nothing; requests without the token or with a foreign `Host` are refused;
and a session walked from request to `solutions` folds to a schema-valid state.
If accepted, the import rule joins the enforcement owned by
[#216](https://github.com/tinix84/frameshift/issues/216).
