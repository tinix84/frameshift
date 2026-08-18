# Solution-generation engine

## Objective

Generate a diverse, traceable option set that addresses the approved frame and causal leverage points while separating exploration from evaluation.

## Inputs

Working frame, causal graph, leverage points, constraints, existing proposals, reusable assets/platforms, and capability policy.

## Method

### Diverge

Generate interventions across relevant levels:

- remove or reduce the need;
- change demand, behavior, or operating policy;
- change process, sourcing, or supply chain;
- reuse a platform or standard architecture;
- modularize or stage delivery;
- change subsystem/component design;
- add redundancy, buffering, or monitoring;
- transfer, share, or accept risk; and
- combine compatible mechanisms.

Use morphological decomposition when the problem has separable functions. Each dimension should describe a function or decision, not a vendor choice.

### De-anchor

Include a “no change / learn first” baseline, a minimal intervention, and at least one option outside the original boundary. Do not generate cosmetic variants merely to reach a count.

### Screen only for hard feasibility

During generation, reject only demonstrable hard-constraint violations. Preferences and uncertain constraints remain visible for later evaluation.

### Trace

Every option names the frame, leverage point, hypothesized mechanism, prerequisites, constraints touched, risks introduced, evidence basis, reversibility, and next validation step.

## Output

An option portfolio, compatibility/conflict map, feasibility unknowns, and suggested prototypes or evidence actions.

## Human gate

The human may merge, split, edit, reject, or request additional diversity. The system must explain which leverage levels are underrepresented.

## Quality checks

- Options are structurally distinct.
- At least one baseline is present.
- Options connect to causal claims rather than free association.
- Hard constraints cite their owner/source.
- No option is called “best” before criteria and validation.
