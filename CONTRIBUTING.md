# Contributing to FrameShift

FrameShift welcomes design notes, fixtures, documentation, adapters, and implementation work.

## Before opening a change

- Search existing issues and ADRs.
- For a substantial behavior or interface change, open a design issue before implementation.
- Do not include confidential problem statements, proprietary engineering data, personal data, or model credentials in fixtures.

## Development workflow

1. Fork or branch from `main` using `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, or `chore/<topic>`.
2. Keep the change focused and update the relevant specification, schema, example, and evaluation together.
3. Run:

   ```sh
   python scripts/validate_repo.py
   python evals/run.py
   ```

4. Open a pull request describing the user outcome, contract changes, validation, and risks.

## Architecture decisions

Use `docs/adr/0000-template.md` for decisions that change domain boundaries, canonical contracts, persistence, security posture, or portability. Accepted ADRs are immutable; supersede them with a new ADR.

## Issue labels and priority

- `P0`: blocks the first safe vertical slice or exposes critical risk.
- `P1`: required for the first usable alpha.
- `P2`: important after the core loop works.
- `P3`: exploratory or optional.

Use one type label (`type:feature`, `type:architecture`, `type:docs`, `type:security`, `type:test`) and one area label when possible.

## Definition of done

A change is documented, contract-compatible, evaluated at the appropriate level, free of committed secrets or sensitive fixtures, and reviewable without relying on hidden model reasoning.
