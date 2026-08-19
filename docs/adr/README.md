# Architecture decision records

ADRs capture durable, cross-cutting decisions. Status values are `proposed`, `accepted`, `deprecated`, or `superseded`. Accepted ADRs are not edited to change history; a later ADR supersedes them.

- [ADR-0001: Canonical provider-neutral domain model](0001-provider-neutral-domain-model.md)
- [ADR-0002: Explicit state machine and human gates](0002-state-machine-human-gates.md)
- [ADR-0003: Typed property graph with Mermaid views](0003-typed-graph-mermaid-view.md)
- [ADR-0004: Event history plus deterministic checkpoints](0004-events-and-checkpoints.md)
- [ADR-0005: Capability broker for tools](0005-capability-broker.md)
- [ADR-0006: Schema-constrained engine results](0006-schema-constrained-results.md)
- [ADR-0007: No chain-of-thought persistence](0007-no-chain-of-thought-persistence.md)
- [ADR-0008: Modular monolith first](0008-modular-monolith-first.md)
- [ADR-0009: MCP server as the runtime boundary](0009-mcp-server-runtime-boundary.md)
- [ADR-0010: Four reasoning engines, framing first](0010-four-reasoning-engines.md)
- [ADR-0011: Problem framing is solution-neutral](0011-solution-neutral-problem-framing.md)

## Supersession

Accepted ADRs are never edited, so a superseded ADR carries no pointer to the ADR that overtook it. This table is the only place that relationship is recorded, and it is asserted by the check paired with the superseding ADR.

| Superseded | By | Extent |
|---|---|---|
| [ADR-0001](0001-provider-neutral-domain-model.md) | [ADR-0009](0009-mcp-server-runtime-boundary.md) | In part. Canonical provider-neutral state stands; the per-provider adapter layer is replaced by MCP. |
| [ADR-0005](0005-capability-broker.md) | [ADR-0009](0009-mcp-server-runtime-boundary.md) | In part. Policy, approval binding, and provenance stand; discovery, schema publication, and invocation move to MCP. |
| [ADR-0006](0006-schema-constrained-results.md) | [ADR-0009](0009-mcp-server-runtime-boundary.md) | In part. The `EngineResult` envelope stands; constraint moves to the tool input schema and shape-only repair narrows to what MCP validation does not cover. |
