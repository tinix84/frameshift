# Decision and validation engine

## Objective

Help humans compare options transparently, challenge a provisional selection, and define evidence that can confirm or reverse it.

## Inputs

Approved frame, option portfolio, criteria, hard constraints, assessments, risks, evidence, stakeholder roles, and decision authority.

## Method

1. Confirm the decision statement, owner, deadline, reversibility, and consequence level.
2. Separate hard constraints from preferences and uncertain assumptions.
3. Have humans define criteria, measurement direction, thresholds, and relative importance.
4. Assess each option with values or bands, evidence, method, and uncertainty.
5. Apply the selected comparison method; keep raw assessments visible.
6. Run sensitivity over uncertain values, weights, and disputed constraints.
7. Conduct pre-mortem, failure-mode, regret, and second-order-effect checks.
8. Identify dominated options and trade-offs without hiding minority views.
9. Recommend one of: decide, prototype, gather evidence, negotiate criteria, or reframe.
10. Produce a validation/monitoring plan with triggers for revisiting the decision.

## Comparison methods

Supported methods may include constraint filtering, qualitative trade-off matrix, weighted multi-criteria analysis, Pareto frontier, expected value, minimax regret, and scenario analysis. The method, assumptions, and limitations are recorded. Weighted scores never replace veto constraints or accountable judgment.

## Decision record

Records frame digest, considered options, criteria owners, assessments, uncertainties, sensitivity findings, selected option, rationale, dissent, approvals, conditions, validation plan, and revisit triggers.

## Human gate

Only an authorized human can approve a decision. Approval binds the exact decision record digest and revision. Consequential decisions may require multiple roles or separation of proposer and approver according to workspace policy.

## Quality checks

- No stale approval after input changes.
- Material assumptions are included in sensitivity or validation plans.
- A rejected option retains its rejection basis.
- Recommendation language matches evidence strength.
- The selected action has success, failure, and reconsideration signals.
