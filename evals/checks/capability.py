"""Restoring across runtimes reports what changed, and refuses a downgrade (#22).

Step 7 of the restore algorithm is "report capability differences and pending
approvals". Pending approvals was already reported; this is the other half.

A checkpoint records the capability profile it was taken under, and each adapter
declares what it offers. Restoring the reference checkpoint into `claude-code`
gains three capabilities including `code.execute.sandboxed`; restoring a
`claude-code` checkpoint into `generic` loses them. Neither was visible.

Most differences are information: nothing auto-executes on restore, so a gain is
not unsafe — but an invisible gain is how a capability profile stops meaning
anything. Two differences are not information at all:

- A **weakened approval requirement**. Work that required a human on every call,
  offered by the new adapter under policy, is ADR-0002's gate crossed by
  changing runtimes — which is the thing ADR-0004 exists to prevent.
- An **escalated side effect**. The same capability id doing more damage under
  the new adapter is the same failure in another dimension.

Those refuse. A refusal here is not corruption and not a limit, so it carries
its own code.
"""

from __future__ import annotations

DOWNGRADE = "capability_downgrade_refused"

# Mirrored from the enums in `schemas/capability-manifest.schema.json`, weakest
# gate first and least severe first. `evals/test_capability.py` asserts both
# still match the schema, so an enum gaining a value cannot silently order
# itself last here.
APPROVAL_STRENGTH = ("never", "policy", "each_call")
SIDE_EFFECT_SEVERITY = ("none", "reversible", "external", "irreversible")


def by_id(profile: dict) -> dict[str, dict]:
    return {
        item["id"]: item
        for item in profile.get("capabilities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _rank(order: tuple[str, ...], value: object) -> int | None:
    return order.index(value) if value in order else None


def profile_differences(recorded: dict, available: dict) -> dict:
    """What changed between the profile a checkpoint records and one on offer."""
    before, after = by_id(recorded), by_id(available)
    reported: list[str] = []
    refused: list[str] = []

    if recorded.get("profile_id") != available.get("profile_id"):
        reported.append(
            f"profile changed: recorded {recorded.get('profile_id')!r}, "
            f"adapter offers {available.get('profile_id')!r}"
        )

    for name in sorted(set(before) - set(after)):
        reported.append(f"capability {name} is recorded but not offered by this adapter")
    for name in sorted(set(after) - set(before)):
        reported.append(f"capability {name} is offered by this adapter but not recorded")

    for name in sorted(set(before) & set(after)):
        was, now = before[name], after[name]
        if was.get("available") and not now.get("available"):
            reported.append(f"capability {name} was available and is not offered as available")

        was_gate, now_gate = _rank(APPROVAL_STRENGTH, was.get("approval")), _rank(
            APPROVAL_STRENGTH, now.get("approval")
        )
        if was_gate is not None and now_gate is not None and now_gate < was_gate:
            refused.append(
                f"{DOWNGRADE}: capability {name} approval weakened from "
                f"{was['approval']!r} to {now['approval']!r}"
            )

        was_effect, now_effect = _rank(SIDE_EFFECT_SEVERITY, was.get("side_effect")), _rank(
            SIDE_EFFECT_SEVERITY, now.get("side_effect")
        )
        if was_effect is not None and now_effect is not None and now_effect > was_effect:
            refused.append(
                f"{DOWNGRADE}: capability {name} side_effect escalated from "
                f"{was['side_effect']!r} to {now['side_effect']!r}"
            )

    return {"reported": reported, "refused": refused}


def _apply(document: dict, mutations: list[dict]) -> None:
    for mutation in mutations:
        container: object = document
        for key in mutation["path"][:-1]:
            container = container[key]
        container[mutation["path"][-1]] = mutation["value"]


def capability_compatibility(case: dict, load) -> list[str]:
    """Compare a checkpoint's recorded profile against the adapter restoring it."""
    checkpoint = load(case["artifact"])
    adapter_profile = load(case["adapter"])
    expect = case["expect"]
    errors: list[str] = []

    recorded = checkpoint.get("capability_profile")
    if recorded is None:
        return [f"{case['artifact']} records no capability_profile to compare"]

    _apply(recorded, case.get("mutate_recorded", []))
    _apply(adapter_profile, case.get("mutate_adapter", []))

    result = profile_differences(recorded, adapter_profile)
    outcome = "refused" if result["refused"] else "compatible"
    if outcome != expect["outcome"]:
        errors.append(
            f"restore is {outcome}, case expects {expect['outcome']}: "
            f"{result['refused'] or result['reported'] or 'no difference'}"
        )

    for fragment in expect.get("reported_naming", []):
        if not any(fragment in item for item in result["reported"]):
            errors.append(f"expected a reported difference naming {fragment}, got {result['reported']}")
    for fragment in expect.get("refused_naming", []):
        if not any(fragment in item for item in result["refused"]):
            errors.append(f"expected a refusal naming {fragment}, got {result['refused']}")
    if expect.get("no_differences") and result["reported"]:
        errors.append(f"expected no differences, got {result['reported']}")

    return errors
