"""Turn checkpoint evidence and broker authorization into a restore plan."""

from __future__ import annotations

from frameshift.broker import prompt_change_refusals


def plan_restore(
    checkpoint: dict,
    persistence_plan: dict,
    contract_differences: list[str],
    *,
    published_registry_supplied: bool,
    confirmed_prompt_change_ids: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """Own reasoning eligibility; persistence supplies evidence, broker supplies authority."""
    plan = dict(persistence_plan)
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
    plan["authorization_refusals"] = prompt_change_refusals(
        checkpoint,
        confirmed_prompt_change_ids,
    )
    plan["reasoning_allowed"] = not (
        plan["contract_differences"] or plan["authorization_refusals"]
    )
    return plan
