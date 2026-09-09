"""Prompt identity determines reasoning eligibility, never inspection integrity."""

from pathlib import Path

from frameshift.bootstrap import published_identities
from frameshift.persistence import compatibility, encode, restore

ROOT = Path(__file__).resolve().parents[2]


def prompt_restore(case: dict, load) -> list[str]:
    checkpoint = load(case["artifact"])
    mutation = case.get("mutation")
    if mutation == "missing_prompt":
        checkpoint["contracts"]["prompts"]["problem_framing"]["id"] = "frameshift.missing.v2"
        checkpoint = encode(checkpoint)
    elif mutation == "unapproved_version_change":
        checkpoint["prompt_version_changes"] = []
        checkpoint = encode(checkpoint)
    elif mutation is not None:
        return [f"unknown prompt-restore mutation {mutation!r}"]

    plan = restore(
        checkpoint,
        {},
        installed_prompts=compatibility.installed_prompts(),
        published_prompts=published_identities(ROOT / "prompts" / "releases"),
        confirmed_prompt_change_ids=set(case.get("confirmed_prompt_change_ids", [])),
    )
    expected = case["expect"]
    errors: list[str] = []
    if plan["outcome"] != expected["outcome"]:
        errors.append(f"restore is {plan['outcome']}, expected {expected['outcome']}")
    if plan["reasoning_allowed"] != expected["reasoning_allowed"]:
        errors.append(
            f"reasoning_allowed is {plan['reasoning_allowed']}, expected {expected['reasoning_allowed']}: "
            f"{plan['contract_differences']}"
        )
    fragment = expected.get("difference_contains")
    if fragment and not any(fragment in item for item in plan["contract_differences"]):
        errors.append(f"expected a contract difference naming {fragment!r}, got {plan['contract_differences']}")
    return errors
