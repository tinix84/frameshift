# Claude Code bootstrap

Read and follow `AGENTS.md` first. Then read `adapters/claude-code/bootstrap.md` and the issues referenced by the task.

Canonical state lives in versioned JSON artifacts, not the transcript. Never expose or persist private chain-of-thought. Record only concise, user-auditable rationale objects defined by the schemas.

## Agent skills

### Issue tracker

Issues, specs, and product requirements live as GitHub issues in `tinix84/frameshift`, worked through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles keep their default names — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` — and all five exist on the repository. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repository root. See `docs/agents/domain.md`.

## Decision log

Every ADR is paired with the issue that makes it verifiable; ADR-0008 is a wayfinder map because its decision is not yet takeable.

| ADR | Date | Decision | Made verifiable by |
|---|---|---|---|
| [0001](docs/adr/0001-provider-neutral-domain-model.md) | 2026-08-18 | Canonical provider-neutral domain model | [#26](https://github.com/tinix84/frameshift/issues/26) |
| [0002](docs/adr/0002-state-machine-human-gates.md) | 2026-08-18 | Explicit state machine and human gates | [#27](https://github.com/tinix84/frameshift/issues/27) |
| [0003](docs/adr/0003-typed-graph-mermaid-view.md) | 2026-08-18 | Typed property graph with Mermaid views | [#28](https://github.com/tinix84/frameshift/issues/28) |
| [0004](docs/adr/0004-events-and-checkpoints.md) | 2026-08-18 | Event history plus deterministic checkpoints | [#29](https://github.com/tinix84/frameshift/issues/29) |
| [0005](docs/adr/0005-capability-broker.md) | 2026-08-18 | Capability broker for tools | [#30](https://github.com/tinix84/frameshift/issues/30) |
| [0006](docs/adr/0006-schema-constrained-results.md) | 2026-08-18 | Schema-constrained engine results | [#31](https://github.com/tinix84/frameshift/issues/31) |
| [0007](docs/adr/0007-no-chain-of-thought-persistence.md) | 2026-08-18 | Never persist private chain-of-thought | [#32](https://github.com/tinix84/frameshift/issues/32) |
| [0008](docs/adr/0008-modular-monolith-first.md) | 2026-08-18 | Start as a modular monolith | map [#33](https://github.com/tinix84/frameshift/issues/33) |
| [0009](docs/adr/0009-mcp-server-runtime-boundary.md) | 2026-08-19 | MCP server as the runtime boundary; supersedes ADR-0001, ADR-0005, ADR-0006 in part | [#67](https://github.com/tinix84/frameshift/issues/67) |
| [0010](docs/adr/0010-four-reasoning-engines.md) | 2026-08-19 | Four reasoning engines, framing first | [#68](https://github.com/tinix84/frameshift/issues/68) |
| [0011](docs/adr/0011-solution-neutral-problem-framing.md) | 2026-08-19 | Problem framing is solution-neutral | [#69](https://github.com/tinix84/frameshift/issues/69) |
