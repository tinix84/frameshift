# ADR-0005: Capability broker for tools

- Status: accepted; superseded in part by ADR-0009 (discovery, schema publication, and invocation move to MCP; policy, approval binding, and provenance stand)
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

Agent runtimes expose different tools, permissions, and names. Letting model-generated tool calls execute directly creates portability, authorization, and injection risks.

## Decision

Workflows request stable semantic capabilities. A broker maps available implementations, validates schemas, enforces workspace/actor policy, obtains bound approvals, executes with scoped credentials, validates output, and records provenance.

## Consequences

Every integration needs a manifest and mapping. Missing tools become explicit capability gaps. The broker provides one enforcement point for least privilege, data destination disclosure, idempotency, and audit.

## Alternatives considered

- Use native runtime tools directly: less code but inconsistent and difficult to govern.
- Standardize only tool names: ignores permissions, data classes, side effects, and schemas.

## Validation

Conformance tests cover unavailable tools, policy denial, injected tool output, stale approval, retry/idempotency, and provenance.
