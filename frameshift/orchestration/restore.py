"""Turn checkpoint evidence and broker authorization into a restore plan."""

from __future__ import annotations

from frameshift.broker import prompt_change_refusals


def plan_restore(
    checkpoint: dict,
    persistence_plan: dict,
    contract_differences: list[str],
    *,
    published_registry_supplied: bool,
    prompt_change_confirmations=(),
) -> dict:
    """Own reasoning eligibility; persistence supplies evidence, broker supplies authority.

    The capability comparison is part of that evidence (#217): the restoring
    adapter's profile was compared against the recorded one in persistence, and
    the plan carries its differences, or its refusal, through to the caller.
    """
    plan = dict(persistence_plan)
    plan["capability_differences"] = list(persistence_plan.get("capability_differences", []))
    plan["contract_differences"] = []
    plan["authorization_refusals"] = []
    plan["reasoning_allowed"] = False
    if plan["outcome"] == "refused":
        return plan

    plan["contract_differences"] = list(contract_differences)
    if not published_registry_supplied:
        plan["contract_differences"].append(
            "the published prompt registry was not supplied, so new reasoning is blocked"
        )
    declined = plan.get("capability_comparison_declined")
    if declined or (isinstance(checkpoint.get("capability_profile"), dict) and declined is not False):
        # Declining to compare is not passing the comparison (#125, #217), and
        # a plan that does not say it compared is read as one that did not.
        plan["contract_differences"].append(
            "the restoring adapter's capability profile was not offered, so new reasoning is blocked"
        )
    plan["authorization_refusals"] = prompt_change_refusals(
        checkpoint,
        prompt_change_confirmations,
    )
    plan["reasoning_allowed"] = not (
        plan["contract_differences"] or plan["authorization_refusals"]
    )
    return plan
