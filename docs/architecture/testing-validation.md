# Testing and validation strategy

## Quality model

FrameShift cannot prove that an LLM answer is correct. It can validate structure, invariants, provenance, workflow safety, reproducibility, and task-specific outcome measures.

## Test pyramid

1. **Schema tests:** valid/invalid JSON fixtures for every contract.
2. **Domain tests:** graph integrity, state transitions, approval binding, constraint semantics, and migrations.
3. **Adapter conformance:** the same request/fixture across runtime adapters.
4. **Engine contract tests:** proposals include required roles, uncertainty, provenance, and next actions.
5. **Scenario evaluations:** expert-reviewed framing, causal diversity, option diversity, and decision trace quality.
6. **Security tests:** injection, tool authorization, tenant isolation, redaction, replay, and deletion.
7. **Human factors:** correction effort, comprehension, calibrated trust, and facilitator usability.

## Deterministic checks

- JSON validates against declared schema version.
- Object IDs and references are valid.
- A working frame has a matching human approval digest.
- A decision cannot be approved against a stale revision.
- Every external claim carries provenance or an explicit unsupported status.
- Same normalized state produces the same semantic digest.
- Restore and re-checkpoint is a round trip.

## Probabilistic evaluations

Run multiple seeds/models where supported and report distributions, not a single score. Rubrics should cover:

- semantic-role classification accuracy;
- abstraction-level coverage without irrelevant expansion;
- number and independence of causal hypotheses;
- ability to seek discriminating evidence;
- structural diversity and feasibility of options;
- explicit handling of constraints, uncertainty, and counter-evidence;
- preservation of human authority; and
- resistance to instructions embedded in evidence.

## Golden fixtures

Golden files pin contract and invariant expectations, not exact prose. Expected output lists required/forbidden properties and relation patterns. Exact text comparison is limited to deterministic renderers and canonical serialization.

## Release gates

- All schemas and repository links validate.
- Reference evaluation fixtures pass.
- Adapter conformance passes for supported environments.
- No unresolved P0 security or data-loss issue.
- Migration and rollback are exercised.
- New engine/prompt version records evaluation deltas and reviewer sign-off.

## Evaluation governance

Version datasets and rubrics, record conflicts of interest and limitations, prevent benchmark leakage into prompts, separate authors from final reviewers where practical, and retain failed results. Do not optimize solely for a composite score.
