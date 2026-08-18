# Product requirements document

## Summary

FrameShift is an interactive workspace and reasoning runtime that turns an ambiguous request into a validated, auditable decision trace. The first release focuses on engineering problem formulation, causal hypotheses, option generation, and decision validation.

## Jobs to be done

- When I receive a solution-shaped request, help me reveal the outcome and alternative system boundaries before committing architecture.
- When causes are uncertain, help me construct competing causal hypotheses and identify discriminating evidence.
- When selecting an intervention, help me generate genuinely different options and compare them transparently.
- When a session spans people, models, or tools, preserve the canonical state and approvals without relying on chat history.

## Functional requirements

| ID | Requirement | Acceptance signal |
|---|---|---|
| FR-01 | Classify intake statements by semantic role | User can correct every classification |
| FR-02 | Build a why/how abstraction ladder | Each level identifies outcome, boundary, and assumptions |
| FR-03 | Propose alternative problem frames | At least three structurally distinct frames when evidence allows |
| FR-04 | Represent causal models as typed graphs | Nodes and edges carry provenance, confidence, and status |
| FR-05 | Track competing hypotheses | Contradictory hypotheses may coexist without overwrite |
| FR-06 | Generate options at multiple leverage levels | Options are linked to frames and causal claims |
| FR-07 | Evaluate options using criteria, constraints, risks, and uncertainty | Score trace retains inputs and sensitivity notes |
| FR-08 | Require human approval at defined gates | Gate cannot be bypassed by an adapter |
| FR-09 | Persist and resume a session | Canonical checkpoint round-trips across two adapters |
| FR-10 | Export a human-readable decision record | Export distinguishes facts, assumptions, inference, and approval |
| FR-11 | Audit external tool use | Tool request, result digest, provenance, and authorization are recorded |
| FR-12 | Support deletion and configurable retention | User can delete a workspace and verify the event |

## Non-functional requirements

- **Portability:** provider-neutral JSON contracts and capability negotiation.
- **Reliability:** operations are idempotent by request ID; checkpoints are content-addressed.
- **Security:** untrusted-data isolation, least-privilege tools, redaction, and approval gates.
- **Auditability:** every material claim links to origin or is marked as an assumption/inference.
- **Accessibility:** keyboard-complete interaction and WCAG 2.2 AA target for the future UI.
- **Performance:** streaming first response under 2 seconds when the runtime allows; checkpoint write under 500 ms excluding remote storage.
- **Observability:** trace engine versions, model/adaptor metadata, tool calls, errors, and token/cost metrics without storing hidden reasoning.

## Primary workflow

1. User states a concern or requested solution.
2. System classifies the statement and asks for the desired outcome.
3. Framing engine proposes an abstraction ladder and candidate frames.
4. Human selects, edits, or rejects the working frame.
5. Causal engine builds competing explanations and evidence requests.
6. Solution engine generates options across leverage levels.
7. Decision engine applies criteria, constraints, risks, and sensitivity checks.
8. Human approves a decision, asks for evidence, or loops to another frame.
9. System writes a checkpoint and decision record.

## Release slices

### M0 — Contract foundation

Schemas, deterministic checkpoints, adapter contract, fixture harness, and a CLI-free reference flow.

### M1 — Framing vertical slice

Intake → classification → ladder → frame approval → checkpoint, with Codex and Claude Code bootstrap validation.

### M2 — Evidence and causal graph

Typed graph editing, competing hypotheses, provenance, contradiction, and evidence planning.

### M3 — Options and decision

Morphological option generation, constraints, multi-criteria comparison, sensitivity, and decision export.

### M4 — Collaborative alpha

Shared workspace, roles, access control, retention, audit export, and usability evaluation.

## Metrics

- Frame revision rate after the abstraction ladder (learning signal, not a quality score).
- Proportion of decisions with at least two alternatives and one counter-hypothesis.
- Provenance coverage of material claims.
- Cross-runtime checkpoint round-trip success.
- Human override and correction rate by engine.
- Evaluation pass rate for invariants and safety gates.
- Time from intake to approved working frame.

## Risks

- Fluent output creates false confidence: mitigate with evidence status, uncertainty, and human gates.
- Users overfit to a rigid ontology: keep types minimal and extensible.
- Portability becomes lowest-common-denominator behavior: allow adapter extensions outside canonical state.
- Sensitive engineering data leaks to model providers: support local policies, redaction, and runtime disclosure.
- Scoring disguises value judgments: expose criteria ownership, weights, and sensitivity.
