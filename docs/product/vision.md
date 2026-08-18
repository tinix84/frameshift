# Product vision

## Vision

FrameShift makes rigorous systems reasoning accessible, collaborative, and inspectable. It helps people spend less effort optimizing the wrong solution and more effort selecting the right problem boundary, evidence, and intervention.

## Problem

People commonly present a requested artifact as if it were the problem: a converter specification, a motor change, a new workflow, or an AI feature. Starting there collapses the solution space. Teams optimize a component while the desired outcome may be vehicle margin, cycle time, safety, customer value, or operational resilience.

Existing chat assistants can suggest alternatives but usually lack durable problem objects, explicit abstraction changes, evidence provenance, deterministic checkpoints, and decision ownership. Their reasoning is difficult to compare across models or resume across tools.

## Target users

- Systems, product, manufacturing, operations, and software engineers.
- Technical program and product leaders coordinating cross-functional decisions.
- Facilitators conducting root-cause, value-engineering, architecture, or trade-off workshops.
- Researchers studying human–AI collaborative reasoning.

## Principles

1. **Frame before solving.** Identify whether the input is a problem, function, requirement, constraint, assumption, or proposed solution.
2. **Move across boundaries.** Ask “why” to move toward outcomes and “how” to move toward mechanisms.
3. **Separate fact from interpretation.** Claims, evidence, assumptions, and uncertainty are first-class.
4. **Prefer plural hypotheses and options.** Avoid single-chain root-cause theater and first-solution anchoring.
5. **Keep the human accountable.** The tool structures judgment; it does not launder model output into authority.
6. **Make reasoning portable.** A session survives a change of model, provider, interface, or agent runtime.
7. **Earn complexity.** The first useful product is a narrow vertical slice, not a universal ontology.

## Non-goals

- Autonomous approval or execution of consequential engineering decisions.
- Replacing simulation, domain analysis, experiments, certification, or expert review.
- Capturing or exposing private model chain-of-thought.
- Guaranteeing root cause, optimality, correctness, or completeness.
- Building a general-purpose project manager or note-taking system.

## Success

FrameShift succeeds when a team can explain what problem it chose, what alternatives it rejected, what evidence changed its view, where uncertainty remains, and how another runtime can reproduce the same checkpoint.
