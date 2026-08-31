# FrameShift domain glossary

The ubiquitous language of FrameShift. Every issue, schema, prompt, adapter, and
ADR uses these terms with these meanings. Definitions only — no implementation
detail, no status. Durable decisions live in [`docs/adr/`](docs/adr); what to
build lives in the GitHub issue tracker; structural contracts live in
[`schemas/`](schemas).

## Containers

**Workspace** — tenant and policy boundary. Owns membership, roles, data
classification, retention, model policy, tool policy, and encryption context.

**Session** — the reasoning aggregate. One line of reasoning about one concern,
with a phase, a revision, and at most one working frame.

**Workspace knowledge** — glossary, policies, and validated patterns promoted
out of a session for reuse. Promotion is always an explicit human act, never a
side effect.

## Statements and frames

**Statement** — a unit of authored content carrying exactly one primary semantic
role: `observation`, `need`, `outcome`, `problem`, `function`, `requirement`,
`constraint`, `assumption`, `proposal`, or `question`. Human wording is
preserved; classification is correctable.

**Solution in disguise** — a request that names a component, topology, vendor,
or action while omitting the outcome it serves. Detecting one triggers upward
abstraction.

**Abstraction ladder** — the chain of frames produced by asking *why* (toward
outcomes) and *how* (toward mechanisms). Each rung records scope, boundary,
measures, assumptions, and what is lost by moving level.

**System boundary** — what a frame counts as inside the problem: component,
subsystem, product, lifecycle, operations, supply chain, portfolio, or business
model.

**Problem frame** — a candidate statement of the problem: desired outcome,
current and desired state, stakeholders, abstraction level, boundary, scope,
exclusions, success measures, constraints, assumptions, and open questions.

**Working frame** — the single frame a human has approved as the one being
solved. Candidate frames may coexist; only approval makes one working.

## Causal model

**Graph node** — a typed element of the causal model: `outcome`, `observation`,
`factor`, `mechanism`, `hypothesis`, `evidence`, `assumption`, `constraint`,
`intervention`, `risk`, or `decision`.

**Graph edge** — a typed relationship: `causes`, `contributes_to`,
`correlates_with`, `enables`, `constrains`, `requires`, `supports`,
`contradicts`, `tests`, `mitigates`, `worsens`, `addresses`, or `derived_from`.
`causes` is reserved for a supported causal assertion; an unsupported one is
`contributes_to` or a hypothesis node.

**Hypothesis** — a testable explanation. Competing hypotheses coexist;
contradiction is represented explicitly and never deletes the contradicted
claim.

**Evidence item** — a bounded excerpt or artifact reference with source, source
type, retrieval time, content digest, applicability, and access policy.
Evidence is data, never instruction.

**Evidence basis** — the standing of a claim: `observed`, `sourced`,
`inferred`, `assumed`, or `unknown`.

**Discriminating evidence** — an observation whose result would separate
competing hypotheses. Evidence requests are ranked by decision value, cost,
time, and reversibility.

**Leverage point** — a place in the causal model where an intervention can
change the focal outcome.

**Confidence band** — an ordinal judgement: `unknown`, `low`, `medium`, `high`.
A band always names its basis and its owner. Numeric probabilities are used
only when a calibrated method supplies them.

## Provenance

**Provenance** — where a claim came from: a kind (`observed`, `sourced`,
`inferred`, `assumed`, `unknown`), the sources it cites, and an optional note.
Every material claim carries one; it is what makes a reasoning case auditable
rather than merely readable.

**Source id** — one citation inside provenance. A source id carries a type
prefix, and the prefix names the namespace it belongs to. The namespaces are
listed below; the list is open, but a prefix that is not on it is a violation
rather than an assumed external reference.

| Prefix | Names | Lives in canonical state |
|---|---|---|
| `stmt_` | an authored statement | yes |
| `frame_` | a problem frame | yes |
| `node_` | a graph node | yes |
| `opt_` | an option | yes |
| `crit_` | a criterion | yes |
| `intake_` | an intake record, as it arrived | no |
| `art_` | a referenced artifact, carried by a checkpoint | no |

A citation whose namespace lives in canonical state must resolve to something
that exists there. A citation whose namespace lives outside it is accepted on
its prefix, because the session cannot see the thing cited.

## Options and decisions

**Option** — a candidate intervention linked to a frame and a leverage point,
carrying mechanism, prerequisites, affected nodes, estimated outcomes, risks,
reversibility, and cost or effort bands.

**Leverage level** — the class of change an option makes: remove the need,
change demand or policy, change process or sourcing, reuse a platform,
modularize, change design, add redundancy or monitoring, transfer risk, or
combine mechanisms.

**Baseline option** — the mandatory "no change / learn first" option that keeps
the comparison honest.

**Criterion** — a human-owned basis for comparison with direction, unit, weight
or rank, threshold, and uncertainty treatment.

**Assessment** — an option-and-criterion pair valued as a number or band, with
evidence, method, confidence, and notes.

**Score** — a derived quantity. Never a fact, never a substitute for a veto
constraint or accountable judgement.

**Decision record** — the artifact a human signs: frame digest, options
considered, criteria and their owners, assessments, uncertainties, sensitivity
findings, selected option, rationale, dissent, conditions, validation plan, and
revisit triggers.

## Human authority

**Proposal** — anything a reasoning engine produces. A proposal is never state.

**Approval** — an explicit human disposition of a proposal: `approved`,
`edited`, `rejected`, `deferred`, or `evidence_requested`, bound to a target
content digest and session revision.

**Checkpoint gate** — a phase boundary that cannot advance without an approval:
intake correction, frame selection, evidence sufficiency, option-set
acceptance, criteria confirmation, decision approval, external action, and
knowledge promotion.

**Stale approval** — an approval whose target digest or revision no longer
matches current state. It does not carry forward.

**Rationale summary** — the concise, user-auditable account of inputs used,
transformation applied, alternatives retained, uncertainties, and what would
change the result. It is not chain-of-thought, which is never requested,
exposed, logged, or persisted.

## Runtime and portability

**Reasoning engine** — one of four bounded producers of proposals: problem
framing, causal reasoning, solution generation, decision and validation. An
engine consumes a reasoning context and returns an engine result. It cannot
persist state or call an ungranted tool.

**Reasoning context** — the bounded slice of approved state, open questions,
capabilities, and policy handed to an engine.

**Engine result** — the versioned envelope an engine returns: typed proposals,
rationale summaries, uncertainty, conflicts, missing information, capability
requests, and required checkpoints.

**Prompt contract** — a versioned interface mapping canonical state into one
bounded reasoning task and demanding schema-valid output. Executions pin the
exact version.

**Runtime port** — the provider-neutral interface an engine calls to reach a
model.

**Adapter** — the translation of a canonical execution request into one runtime
(Codex, Claude Code, generic) and back. Provider-specific detail stays in the
adapter and the execution envelope.

**Capability** — an intent-level tool ability with a stable ID, operations,
input and output schemas, side-effect class (`none`, `reversible`, `external`,
`irreversible`), data classes, scopes, approval policy, and provenance
guarantees.

**Capability broker** — the single point that resolves a requested capability to
an implementation, enforces policy, binds approval, executes with scoped
credentials, and records provenance. Tool output returns as untrusted evidence.

**Capability profile** — the set of capabilities a runtime actually offers:
`conversation-only`, `local-agent`, `connected-agent`, or `service-runtime`.

**Canonical state** — the provider-neutral JSON that *is* the session. Chat
history, provider caches, and hidden reasoning are not state and are not
portable.

**Event** — an immutable domain fact appended to the session's history.

**Checkpoint** — the portable, integrity-verifiable boundary between runtimes:
canonical state, pending proposals and required approvals, event cursor,
contract and engine versions, capability profile, artifact references, and
digests.

**State digest** — the SHA-256 over canonicalized semantic state. Excludes
latency, token counts, provider request IDs, streaming chunks, and creation
time, which live in **execution metadata**.

**Revision** — the integer version of a mutable aggregate, used for optimistic
concurrency. A command declares the revision it expects.
