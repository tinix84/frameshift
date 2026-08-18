# ADR-0003: Typed property graph with Mermaid views

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

Reasoning contains branching hypotheses, feedback, evidence, contradiction, interventions, and decisions. A plain document or Five Whys chain loses these relationships. Mermaid is portable and readable but is not a robust database format.

## Decision

Use a typed JSON property graph as canonical state. Generate deterministic Mermaid diagrams as views and documentation artifacts. Permit cycles and explicit contradiction; validate referential integrity and provenance.

## Consequences

Graph state supports multiple views and machines can validate it. Renderers must handle size and accessibility. Mermaid input is treated as untrusted and never directly becomes canonical state.

## Alternatives considered

- Mermaid as source of truth: readable but weak typing, migration, and security.
- Relational tables only: viable storage but awkward interchange and graph-oriented reasoning.
- Dedicated graph database immediately: unnecessary operational complexity for the first slice.

## Validation

Graph fixtures cover cycles, contradiction, invalid references, deterministic rendering, and accessible list equivalents.
