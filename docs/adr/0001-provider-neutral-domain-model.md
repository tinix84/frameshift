# ADR-0001: Canonical provider-neutral domain model

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

FrameShift must resume across Codex, Claude Code, API-hosted models, and future runtimes. Provider transcripts and tool-call formats are incompatible and contain nondurable details.

## Decision

Canonical session state, engine inputs/outputs, capabilities, and checkpoints use versioned provider-neutral JSON contracts. Provider-specific messages, tool names, request IDs, and token metrics stay inside adapters and execution envelopes.

## Consequences

Adapters require explicit normalization and may not expose every native feature. State is portable and testable without a model provider. Provider extensions are allowed only in namespaced `extensions` that cannot alter canonical safety semantics.

## Alternatives considered

- Adopt one provider's conversation format: fastest initially but creates lock-in and weak portability.
- Store raw transcripts as state: easy to capture but hard to validate, migrate, minimize, or safely resume.

## Validation

Round-trip the same checkpoint through at least two adapters and compare canonical digests and invariants.
