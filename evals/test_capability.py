#!/usr/bin/env python3
"""Tests that capability comparison refuses downgrades and reports the rest.

The distinction is the point: most differences are information, and two are
refusals. A check that reported all of them would let a gate be crossed by
changing runtimes; one that refused all of them would make restore useless.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import capability, schema  # noqa: E402

GENERIC = "adapters/generic/capabilities.json"
CLAUDE_CODE = "adapters/claude-code/capabilities.json"


def recorded_profile() -> dict:
    return run.load("evals/fixtures/reference.checkpoint.json")["capability_profile"]


class OrderingTests(unittest.TestCase):
    """The orderings are mirrors of the schema, not independent opinions."""

    def setUp(self) -> None:
        manifest = schema.load_schema("capability-manifest.schema.json")
        self.properties = manifest["properties"]["capabilities"]["items"]["properties"]

    def test_approval_strength_matches_the_schema_enum(self) -> None:
        self.assertEqual(
            set(capability.APPROVAL_STRENGTH), set(self.properties["approval"]["enum"])
        )

    def test_side_effect_severity_matches_the_schema_enum(self) -> None:
        self.assertEqual(
            set(capability.SIDE_EFFECT_SEVERITY), set(self.properties["side_effect"]["enum"])
        )

    def test_never_is_the_weakest_gate_and_each_call_the_strongest(self) -> None:
        self.assertEqual(capability.APPROVAL_STRENGTH[0], "never")
        self.assertEqual(capability.APPROVAL_STRENGTH[-1], "each_call")

    def test_none_is_the_least_severe_effect_and_irreversible_the_most(self) -> None:
        self.assertEqual(capability.SIDE_EFFECT_SEVERITY[0], "none")
        self.assertEqual(capability.SIDE_EFFECT_SEVERITY[-1], "irreversible")


class IdenticalProfileTests(unittest.TestCase):
    def test_the_recorded_adapter_yields_no_difference_at_all(self) -> None:
        result = capability.profile_differences(recorded_profile(), run.load(GENERIC))
        self.assertEqual(result["reported"], [])
        self.assertEqual(result["refused"], [])


class ReportedDifferenceTests(unittest.TestCase):
    def test_a_richer_adapter_reports_every_capability_it_adds(self) -> None:
        result = capability.profile_differences(recorded_profile(), run.load(CLAUDE_CODE))
        self.assertEqual(result["refused"], [], "a gain is not a downgrade")
        for name in ("artifact.write", "code.execute.sandboxed", "external.connector"):
            self.assertTrue(any(name in item for item in result["reported"]), name)

    def test_a_poorer_adapter_reports_every_capability_it_lacks(self) -> None:
        result = capability.profile_differences(run.load(CLAUDE_CODE), run.load(GENERIC))
        self.assertEqual(result["refused"], [])
        for name in ("artifact.write", "code.execute.sandboxed"):
            self.assertTrue(
                any(name in item and "not offered" in item for item in result["reported"]), name
            )

    def test_a_capability_becoming_unavailable_is_reported(self) -> None:
        recorded = recorded_profile()
        adapter = copy.deepcopy(run.load(GENERIC))
        adapter["capabilities"][0]["available"] = False
        result = capability.profile_differences(recorded, adapter)
        self.assertTrue(any("not offered as available" in item for item in result["reported"]))
        self.assertEqual(result["refused"], [])

    def test_a_changed_profile_id_is_reported(self) -> None:
        result = capability.profile_differences(recorded_profile(), run.load(CLAUDE_CODE))
        self.assertTrue(any("profile changed" in item for item in result["reported"]))


class RefusedDowngradeTests(unittest.TestCase):
    def test_every_weakening_of_an_approval_gate_is_refused(self) -> None:
        for was, now in (("each_call", "policy"), ("each_call", "never"), ("policy", "never")):
            with self.subTest(was=was, now=now):
                recorded = recorded_profile()
                recorded["capabilities"][0]["approval"] = was
                adapter = copy.deepcopy(run.load(GENERIC))
                adapter["capabilities"][0]["approval"] = now
                result = capability.profile_differences(recorded, adapter)
                self.assertTrue(
                    any("approval weakened" in item for item in result["refused"]), result
                )

    def test_strengthening_an_approval_gate_is_not_refused(self) -> None:
        recorded = recorded_profile()
        recorded["capabilities"][0]["approval"] = "never"
        adapter = copy.deepcopy(run.load(GENERIC))
        adapter["capabilities"][0]["approval"] = "each_call"
        self.assertEqual(capability.profile_differences(recorded, adapter)["refused"], [])

    def test_every_escalation_of_a_side_effect_is_refused(self) -> None:
        for was, now in (
            ("none", "reversible"),
            ("reversible", "external"),
            ("external", "irreversible"),
            ("none", "irreversible"),
        ):
            with self.subTest(was=was, now=now):
                recorded = recorded_profile()
                recorded["capabilities"][0]["side_effect"] = was
                adapter = copy.deepcopy(run.load(GENERIC))
                adapter["capabilities"][0]["side_effect"] = now
                result = capability.profile_differences(recorded, adapter)
                self.assertTrue(
                    any("side_effect escalated" in item for item in result["refused"]), result
                )

    def test_de_escalating_a_side_effect_is_not_refused(self) -> None:
        recorded = recorded_profile()
        recorded["capabilities"][0]["side_effect"] = "irreversible"
        adapter = copy.deepcopy(run.load(GENERIC))
        adapter["capabilities"][0]["side_effect"] = "none"
        self.assertEqual(capability.profile_differences(recorded, adapter)["refused"], [])

    def test_a_refusal_carries_its_own_code(self) -> None:
        recorded = recorded_profile()
        recorded["capabilities"][0]["approval"] = "each_call"
        result = capability.profile_differences(recorded, run.load(GENERIC))
        self.assertTrue(result["refused"])
        self.assertTrue(all(item.startswith(capability.DOWNGRADE) for item in result["refused"]))


class CaseWiringTests(unittest.TestCase):
    CASES = (
        "capability-restore-into-the-recorded-adapter",
        "capability-restore-reports-what-changed",
        "capability-restore-refuses-a-weakened-approval",
        "capability-restore-refuses-an-escalated-side-effect",
    )

    def test_every_declared_case_passes(self) -> None:
        for name in self.CASES:
            with self.subTest(case=name):
                self.assertEqual(run.evaluate(run.load(f"evals/fixtures/{name}.case.json")), [])

    def test_each_refusal_case_is_earned_by_its_mutation(self) -> None:
        for name in self.CASES[2:]:
            with self.subTest(case=name):
                case = run.load(f"evals/fixtures/{name}.case.json")
                case.pop("mutate_recorded", None)
                case.pop("mutate_adapter", None)
                self.assertTrue(run.evaluate(case), "without its mutation the case must fail")

    def test_a_checkpoint_without_a_recorded_profile_is_reported(self) -> None:
        case = run.load("evals/fixtures/capability-restore-into-the-recorded-adapter.case.json")

        def load(relative: str) -> object:
            artifact = run.load(relative)
            if relative == case["artifact"]:
                artifact = {key: value for key, value in artifact.items() if key != "capability_profile"}
            return artifact

        errors = capability.capability_compatibility(case, load)
        self.assertTrue(any("records no capability_profile" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
