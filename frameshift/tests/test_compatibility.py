#!/usr/bin/env python3
"""Tests for contract compatibility on restore (#22 step 6).

A checkpoint pins the prompt contracts it was produced under. Restore it
somewhere those prompts have been deleted, renamed, or rewritten and its
proposals cite reasoning nobody can reproduce. These prove each of those three
is noticed, and that a compatible checkpoint stays quiet.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.persistence import compatibility, restore  # noqa: E402

REFERENCE = ROOT / "evals" / "fixtures" / "reference.checkpoint.json"


def checkpoint() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def artifacts(cp: dict) -> dict[str, bytes]:
    return {
        item["id"]: (ROOT / item["uri"]).read_bytes().replace(b"\r\n", b"\n")
        for item in cp.get("artifacts", [])
    }


class InstalledPromptTests(unittest.TestCase):
    def test_both_committed_prompts_are_found(self) -> None:
        installed = compatibility.installed_prompts()
        self.assertEqual(
            set(installed),
            {"frameshift.problem-framing.v1", "frameshift.repair-structured-output.v1"},
        )

    def test_each_carries_its_declared_and_actual_digest(self) -> None:
        for identifier, manifest in compatibility.installed_prompts().items():
            with self.subTest(prompt=identifier):
                self.assertEqual(manifest["body_digest"], manifest["actual_body_digest"])


class CompatibilityTests(unittest.TestCase):
    def test_the_committed_checkpoint_is_compatible(self) -> None:
        self.assertEqual(compatibility.contract_differences(checkpoint()), [])

    def test_a_pinned_prompt_that_is_not_installed_is_reported(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        differences = compatibility.contract_differences(cp)
        self.assertTrue(any("frameshift.deleted.v1" in item for item in differences), differences)
        self.assertTrue(any("cannot be reproduced" in item for item in differences))

    def test_a_prompt_pinned_for_the_wrong_engine_is_reported(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["causal_reasoning"] = "frameshift.problem-framing.v1"
        differences = compatibility.contract_differences(cp)
        self.assertTrue(any("declares engine" in item for item in differences), differences)

    def test_a_shared_prompt_may_be_pinned_for_any_engine(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"]["causal_reasoning"] = "frameshift.repair-structured-output.v1"
        self.assertEqual(compatibility.contract_differences(cp), [])

    def test_a_rewritten_prompt_is_reported(self) -> None:
        """Detectable only because a manifest digests its own body (#144)."""
        installed = compatibility.installed_prompts()
        tampered = copy.deepcopy(installed)
        tampered["frameshift.problem-framing.v1"]["actual_body_digest"] = "sha256:" + "0" * 64
        differences = compatibility.contract_differences(checkpoint(), tampered)
        self.assertTrue(any("has been rewritten" in item for item in differences), differences)

    def test_a_checkpoint_pinning_nothing_reports_nothing(self) -> None:
        cp = checkpoint()
        cp["contracts"]["prompts"] = {}
        self.assertEqual(compatibility.contract_differences(cp), [])

    def test_differences_are_reports_and_carry_no_error_code(self) -> None:
        """#126's precedent: a difference is described, only a refusal is coded."""
        sys.path.insert(0, str(ROOT))
        from evals.checks import errors

        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        for item in compatibility.contract_differences(cp):
            first = item.split(":", 1)[0]
            self.assertNotIn(first, errors.VOCABULARY, "a report must not look like a refusal")


class RestorePlanTests(unittest.TestCase):
    def test_the_plan_carries_contract_differences(self) -> None:
        cp = checkpoint()
        plan = restore(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "verified")
        self.assertEqual(plan["contract_differences"], [])

    def test_an_incompatible_checkpoint_still_restores(self) -> None:
        """What is lost is the ability to re-run, not the ability to read."""
        cp = checkpoint()
        cp["contracts"]["prompts"]["problem_framing"] = "frameshift.deleted.v1"
        # Re-encode so the digests still match the edited envelope.
        from frameshift.persistence import encode

        cp = encode(cp)
        plan = restore(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "verified")
        self.assertTrue(plan["contract_differences"])
        self.assertTrue(plan["pending_proposal_ids"])

    def test_a_refused_restore_reports_no_differences(self) -> None:
        cp = checkpoint()
        cp["state"]["title"] = "tampered"
        plan = restore(cp, artifacts(cp))
        self.assertEqual(plan["outcome"], "refused")
        self.assertEqual(plan["contract_differences"], [])


if __name__ == "__main__":
    unittest.main()
