# Human-in-the-loop interaction model

## Ownership

Humans own outcomes, scope, constraints, evidence acceptance, criteria, risk appetite, and decisions. FrameShift owns bookkeeping, structured proposals, consistency checks, alternative generation, and auditability.

## Interaction states

Every proposed object is one of `draft`, `proposed`, `approved`, `rejected`, `superseded`, or `archived`. The UI must visibly distinguish model proposals from committed human-approved state.

## Checkpoints

| Gate | Required human action | Why |
|---|---|---|
| Intake correction | Confirm/edit semantic roles | Classification changes the workflow |
| Frame selection | Approve a frame digest | Sets objective and boundary |
| Evidence sufficiency | Continue, collect, or reframe | Prevents causal fluency becoming fact |
| Option-set acceptance | Accept diversity/scope | Prevents anchoring and omitted categories |
| Criteria confirmation | Own criteria and constraints | Encodes values and authority |
| Decision approval | Sign exact record digest | Consequential accountability |
| External action | Approve scoped tool call | Controls side effects |
| Knowledge promotion | Approve cross-session memory | Controls reuse and privacy |

## Review actions

At each gate a user can approve, edit, reject, defer, request evidence, compare alternatives, or return to an earlier phase. “Approve all” is disallowed for consequential or mixed-sensitivity proposals.

## Explanation design

Show concise rationale summaries: inputs used, transformations applied, evidence status, alternatives considered, uncertainty, and what would change the recommendation. Do not claim to expose hidden chain-of-thought.

## Interruptibility

Long-running engines emit progress and cancellable boundaries. Cancellation cannot commit partial proposals. Tool calls indicate resource, operation, expected effect, data destination, and reversibility before approval.

## Disagreement

Multiple participant views may coexist. Record authorship and dissent. The system may summarize disagreement but cannot invent consensus. Resolution follows workspace decision policy.

## Accessibility and failure recovery

All graph actions need a list/table equivalent. Checkpoints are keyboard reachable, use plain language, and state consequences. After runtime failure, restore the last committed revision and keep uncommitted proposals separately marked.
