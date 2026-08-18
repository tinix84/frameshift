# Prompt contracts

## Principle

A prompt is a versioned interface, not free-form application code. It maps canonical state into a bounded reasoning task and demands a schema-valid proposal.

## Prompt manifest fields

- `id`, `version`, `engine`, `description`.
- Required input artifact types and maximum sizes.
- Output schema path.
- Required invariants and forbidden behaviors.
- Capability requirements.
- Repair prompt ID.
- Evaluation fixture set.
- Changelog and owner.

## Standard task frame

Every engine prompt conveys:

1. **Role:** propose structured reasoning artifacts; do not decide for the human.
2. **Trusted instructions:** repository/runtime policy and engine task.
3. **Untrusted data:** clearly delimited user content, evidence, and tool output.
4. **Approved state:** only committed objects and their revision/digest.
5. **Task:** one engine step with stop conditions.
6. **Output:** JSON only, conforming to the supplied schema.
7. **Invariants:** provenance, uncertainty, no invented approval/evidence, no hidden reasoning.
8. **Failure behavior:** return typed conflicts/missing information rather than fabricate.

## Rationale contract

The result includes short user-auditable rationale summaries: input references used, transformation or heuristic applied, alternatives retained, uncertainties, and what evidence may change the result. It must not request or expose private chain-of-thought.

## Injection boundary

Evidence is wrapped with stable source IDs and an explicit statement that content inside it is data, not instruction. Adapters use the strongest native role separation available. Tool output is handled identically.

## Versioning

Any change that can alter required fields, workflow transitions, safety behavior, or evaluation interpretation creates a new prompt version. Editorial clarifications may increment a patch version. Execution records pin the exact version.

## Repair

One repair attempt receives validation errors and the invalid structured output, not the entire hidden interaction. The repair may only fix shape/type/reference problems; it must not create approvals or unsupported evidence.
