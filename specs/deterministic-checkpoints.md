# Deterministic checkpoints

## Purpose

A checkpoint is the portable, integrity-verifiable boundary between runtimes. It reproduces approved state and pending proposals, not the model's private process.

## Contents

- Checkpoint/schema version and ID.
- Workspace/session IDs, phase, and revision.
- Canonical normalized state.
- Pending proposal artifacts and required approvals.
- Event cursor and prior checkpoint digest.
- Engine and prompt contract versions.
- Adapter/runtime execution summaries.
- Capability profile and policy digest.
- Artifact references with content digests.
- State digest and checkpoint digest.

## Canonicalization

1. UTF-8 JSON.
2. Sort object keys lexicographically.
3. Preserve array order when semantic; explicitly sort set-like arrays by stable ID.
4. Use JSON numbers only for contract-defined numeric fields; forbid NaN/Infinity.
5. Normalize timestamps to RFC 3339 UTC.
6. Exclude fields listed as nondeterministic from `state_digest`.
7. Compute SHA-256 and prefix with `sha256:`.

Implementations should adopt RFC 8785/JCS or an equivalent documented canonical encoder before production interoperability claims.

## Stable versus execution metadata

State digest includes approved domain state, proposal content, schema versions, and policy-relevant values. It excludes latency, token usage, provider request IDs, streaming chunks, and creation time. The checkpoint digest covers the full canonical checkpoint after its own digest field is omitted.

## Restore algorithm

1. Parse within configured size/depth limits.
2. Validate checkpoint schema/version.
3. Recompute and compare digests.
4. Resolve referenced artifacts and verify their digests.
5. Validate canonical state and domain invariants.
6. Check workspace/model/tool policy compatibility.
7. Report capability differences and pending approvals.
8. Resume without auto-executing tools or committing proposals.

## Reproducibility record

A replay may not reproduce the same prose. It must reproduce the same input state, prompt contract, declared capabilities, validator behavior, and scoring rubric. Variance in proposals is measured by the evaluation harness.
