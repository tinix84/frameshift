# ADR-0009: MCP server as the runtime boundary

- Status: accepted
- Date: 2026-08-19
- Deciders: initial maintainers
- Supersedes: ADR-0001 in part, ADR-0005 in part, ADR-0006 in part

## Context

ADR-0001 through ADR-0008 assumed FrameShift would call models through hand-written adapters for Codex, Claude Code, and API-hosted runtimes. That assumption no longer holds: there is no API access, only Claude Code. Nothing inside FrameShift calls a model.

Claude Code already supplies the model, the agent loop, and the human at the terminal. What it lacks is canonical state, schema validation, an explicit state machine, gates, a typed graph, and portable checkpoints. That is the whole of what FrameShift contributes, and the Model Context Protocol is the interface through which a runtime consumes it.

Three accepted ADRs are partly overtaken. Their decision text stands as written; each carries a `Status` line pointing here and naming the extent, so a reader arriving at ADR-0005 learns it was overtaken without the history being rewritten.

## Decision

FrameShift is an inbound MCP server. Claude Code is the client; FrameShift never calls a model, spawns a runtime, or drives a conversation.

**MCP is the portability layer.** Any MCP-capable runtime is a supported client. The per-provider adapter layer of ADR-0001 dissolves into one protocol implementation.

**Reasoning engines become contracts, not callers.** An engine is a versioned prompt contract plus an MCP tool input schema. The client's model fills the schema; the server validates, gates, persists, and returns the next bounded reasoning context.

**The broker keeps policy and provenance, not plumbing.** MCP's tool layer owns discovery, schema publication, and invocation. The capability broker of ADR-0005 remains as the enforcement point for workspace and actor policy, approval binding, scoped credentials, side-effect classification, and provenance recording.

**Tool input schemas are the primary output constraint.** The `EngineResult` envelope of ADR-0006 stays canonical, but constraint is enforced at the MCP boundary before a handler runs. The one-shot shape-only repair path narrows to what MCP validation does not already cover, and still may not introduce facts.

**Every MCP call is logged mechanically** — tool, argument digest, outcome, violation codes, duration. Never model reasoning, so ADR-0007 is untouched.

**Checkpoints draft lessons; tags promote them.** A checkpoint write emits candidate lessons as drafts. A tag is a named immutable approval bound to a checkpoint digest and revision that sweeps every lesson drafted since the previous tag into workspace knowledge. Knowledge items carry `released_in`; rollback is a superseding tag, never a deletion.

Python is the implementation language, chosen for fluency and reuse rather than as a terminal commitment. The MCP tool contracts, canonical JSON, and `evals/fixtures/` stay language-independent so a later port — most likely Go, if installation friction becomes the binding constraint on adoption — replaces the implementation behind a stable interface.

## Consequences

The outbound path — a FrameShift UI spawning `claude -p --output-format stream-json` — is deliberately deferred. Headless runs consume the operator's own subscription quota, and a distributed FrameShift means each user brings their own Claude Code, so the outbound path is not a route to a hosted product.

Portability is now demonstrated by two MCP clients agreeing on a canonical digest rather than by two hand-written adapters. Capability gaps surface as absent MCP tools. Issues scoped against the adapter framing — #4, #8, #11, #30, #38, #43, #45 — need rescoping.

The application takes a small pinned dependency set (MCP SDK, a Draft 2020-12 validator, import-linter). `scripts/validate_repo.py` and `evals/run.py` stay standard-library only so the repository can be cloned and verified with no install.

## Alternatives considered

- Keep the multi-adapter framing and treat MCP as one adapter among several: preserves ADR-0001 unchanged but pays for provider abstraction that nothing currently exercises.
- Build the outbound subprocess path first: yields a UI with no API key, but is a larger surface and is not required by the first vertical slice.
- Reimplement discovery and invocation inside the broker: duplicates protocol work MCP already specifies and tests.

## Validation

The same checkpoint round-tripped through two MCP clients yields one canonical digest. Tool calls rejected by MCP schema validation never reach a handler. The session log contains no rationale beyond argument digests and violation codes. Promotion of a lesson to workspace knowledge is traceable to exactly one tag.
