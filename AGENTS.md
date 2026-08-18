# Repository agent instructions

These instructions apply to Codex, Claude Code, and other agentic contributors.

## Mission

Build FrameShift as an inspectable, model-agnostic reasoning system. Preserve human agency: the system proposes frames, hypotheses, and options; a human owns objectives, boundary choices, consequential assumptions, and decisions.

## Required working method

1. Read `README.md`, the relevant specification, and applicable ADRs before changing behavior.
2. Keep canonical domain objects provider-neutral and valid against `schemas/`.
3. Do not treat hidden chain-of-thought as product state. Persist concise claims, evidence, assumptions, uncertainties, alternatives, and decision rationale.
4. Put LLM-specific behavior behind an adapter in `adapters/`.
5. Put tool-specific behavior behind the capability contract in `specs/tool-capability-abstraction.md`.
6. Add or update a fixture for any reasoning-contract change.
7. Run `python scripts/validate_repo.py` and `python evals/run.py` before declaring work complete.
8. Create an ADR for a durable, cross-cutting architecture decision; do not rewrite accepted ADRs.

## Safety invariants

- Never silently promote a suggestion into an approved requirement or decision.
- Never invent evidence, citations, tool results, or confidence precision.
- Label inference, assumption, uncertainty, and provenance explicitly.
- Require a human checkpoint before irreversible, externally visible, safety-critical, or high-cost actions.
- Minimize persisted sensitive data and honor redaction and retention policies.

## Change discipline

- Prefer a small vertical slice over speculative infrastructure.
- Keep JSON deterministic: UTF-8, sorted object keys for hashing, no timestamps in semantic equality checks.
- Update contracts and examples together.
- Branch from `main`; use short-lived `feat/`, `fix/`, `docs/`, or `chore/` branches.
