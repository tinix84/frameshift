# Repository agent instructions

These instructions apply to Codex, Claude Code, and other agentic contributors.

## Mission

Build FrameShift as an inspectable, model-agnostic reasoning system. Preserve human agency: the system proposes frames, hypotheses, and options; a human owns objectives, boundary choices, consequential assumptions, and decisions.

## Required working method

1. Read `README.md`, `CONTEXT.md`, the issue you are working from, and applicable ADRs before changing behavior. Contracts and product requirements are issues, not files — see `docs/agents/issue-tracker.md`.
2. Keep canonical domain objects provider-neutral and valid against `schemas/`.
3. Never treat hidden chain-of-thought as product state. Persist concise claims, evidence, assumptions, uncertainties, alternatives, and decision rationale.
4. Put LLM-specific behavior behind an adapter in `adapters/`.
5. Put tool-specific behavior behind the capability contract in issue #21.
6. Add or update a fixture for any reasoning-contract change.
7. Run `python scripts/validate_repo.py` and `python evals/run.py` before declaring work complete.
8. Create an ADR for a durable, cross-cutting architecture decision, add its row to the decision log in `CLAUDE.md`, and do not rewrite accepted ADRs.
9. Use the vocabulary defined in `CONTEXT.md`; a missing term is either invented language or a gap worth recording.

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
- Never restate in a tracked file what an issue, an ADR, or `CONTEXT.md` already owns.
- Branch from `main`; use short-lived `feat/`, `fix/`, `docs/`, or `chore/` branches.
