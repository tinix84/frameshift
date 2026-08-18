# Claude Code bootstrap

Read and follow `AGENTS.md` first. Then read `adapters/claude-code/bootstrap.md` and the issues referenced by the task.

Canonical state lives in versioned JSON artifacts, not the transcript. Do not expose or persist private chain-of-thought. Record only concise, user-auditable rationale objects defined by the schemas.

## Agent skills

Configuration the engineering skills rely on:

- `docs/agents/issue-tracker.md` — where issues live and how to read and write them.
- `docs/agents/triage-labels.md` — the label strings behind the five triage roles.
- `docs/agents/domain.md` — how to consume `CONTEXT.md` and `docs/adr/` before exploring.

## Decision log

| ADR | Date | Decision |
|---|---|---|
| [0001](docs/adr/0001-provider-neutral-domain-model.md) | 2026-08-18 | Canonical provider-neutral domain model |
| [0002](docs/adr/0002-state-machine-human-gates.md) | 2026-08-18 | Explicit state machine and human gates |
| [0003](docs/adr/0003-typed-graph-mermaid-view.md) | 2026-08-18 | Typed property graph with Mermaid views |
| [0004](docs/adr/0004-events-and-checkpoints.md) | 2026-08-18 | Event history plus deterministic checkpoints |
| [0005](docs/adr/0005-capability-broker.md) | 2026-08-18 | Capability broker for tools |
| [0006](docs/adr/0006-schema-constrained-results.md) | 2026-08-18 | Schema-constrained engine results |
| [0007](docs/adr/0007-no-chain-of-thought-persistence.md) | 2026-08-18 | Do not persist private chain-of-thought |
| [0008](docs/adr/0008-modular-monolith-first.md) | 2026-08-18 | Start as a modular monolith |
