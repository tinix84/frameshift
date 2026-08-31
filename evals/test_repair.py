#!/usr/bin/env python3
"""Tests that the repair corpus would fail if the boundary moved.

The corpus proves the current fixtures behave. These prove the rule underneath
it is real: that a second attempt is never taken, that the subset rule catches
an invented referent, and that the validator reading `schemas/` is not silently
passing everything.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import repair, schema  # noqa: E402

VALID = "evals/fixtures/framing-solution-disguised.result.json"
INVALID = "evals/fixtures/repair/wrong-typed-field.invalid.json"
REPAIRED = "evals/fixtures/repair/wrong-typed-field.repaired.json"


def corpus_cases() -> list[dict]:
    cases = [run.load(str(path.relative_to(run.ROOT))) for path in sorted(run.FIXTURES.glob("*.case.json"))]
    return [case for case in cases if case["check"] == "engine_result_repair"]


class SchemaValidatorTests(unittest.TestCase):
    def test_the_reference_result_is_valid(self) -> None:
        self.assertEqual(schema.validate_engine_result(run.load(VALID)), [])

    def test_a_wrong_type_is_reported_with_its_path(self) -> None:
        errors = schema.validate_engine_result(run.load(INVALID))
        self.assertTrue(any("$.input_revision" in error for error in errors), errors)

    def test_an_unknown_property_is_rejected(self) -> None:
        artifact = run.load(VALID)
        artifact["surprise"] = 1
        self.assertTrue(schema.validate_engine_result(artifact))

    def test_an_unsupported_keyword_raises_rather_than_passing(self) -> None:
        with self.assertRaises(schema.UnsupportedSchema):
            schema.validate("x", {"type": "string", "allOf": []}, current="common.schema.json")


class SubsetRuleTests(unittest.TestCase):
    def test_an_identical_repair_introduces_nothing(self) -> None:
        artifact = run.load(VALID)
        self.assertEqual(repair.subset_violations(artifact, copy.deepcopy(artifact)), [])

    def test_dropping_a_referent_is_allowed(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["proposals"] = after["proposals"][:1]
        self.assertEqual(repair.subset_violations(before, after), [])

    def test_a_new_evidence_reference_is_caught(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["proposals"][0]["provenance"]["source_ids"].append("ev_invented")
        self.assertTrue(any("ev_invented" in item for item in repair.subset_violations(before, after)))

    def test_a_new_identifier_is_caught(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["proposals"][0]["id"] = "prop_renamed_001"
        self.assertTrue(any("prop_renamed_001" in item for item in repair.subset_violations(before, after)))

    def test_a_rewritten_frame_question_is_caught_and_names_the_field(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        frame = next(item for item in after["proposals"] if item["kind"] == "problem_frame")
        frame["value"]["question"] = "How might we cut inverter unit cost by 15 percent?"
        violations = repair.subset_violations(before, after)
        self.assertTrue(any("question" in item for item in violations), violations)

    def test_a_rewritten_rationale_summary_is_caught(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["rationale_summaries"][0] = "The intake already names the owned outcome."
        violations = repair.subset_violations(before, after)
        self.assertTrue(any("rationale_summaries" in item for item in violations), violations)

    def test_a_rewritten_note_summary_is_caught(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["uncertainties"][0]["summary"] = "The performance threshold is 250 kW."
        violations = repair.subset_violations(before, after)
        self.assertTrue(any("summary" in item for item in violations), violations)

    def test_a_new_capability_request_is_caught(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["requested_capabilities"] = ["shell.execute"]
        self.assertTrue(any("shell.execute" in item for item in repair.subset_violations(before, after)))


class ShapeRepairTests(unittest.TestCase):
    """Shape repair keeps working: the rule refuses new facts, not new structure."""

    def test_correcting_a_type_is_accepted(self) -> None:
        result = repair.run_repair(run.load(INVALID), run.load(REPAIRED))
        self.assertEqual(result["outcome"], "repaired", result)

    def test_filling_a_missing_enum_is_accepted(self) -> None:
        invalid = run.load(VALID)
        invalid["status"] = "finished"
        repaired = copy.deepcopy(invalid)
        repaired["status"] = "complete"
        result = repair.run_repair(invalid, repaired)
        self.assertEqual(result["outcome"], "repaired", result)

    def test_adding_a_required_empty_array_is_accepted(self) -> None:
        invalid = run.load(VALID)
        del invalid["conflicts"]
        repaired = copy.deepcopy(invalid)
        repaired["conflicts"] = []
        result = repair.run_repair(invalid, repaired)
        self.assertEqual(result["outcome"], "repaired", result)

    def test_dropping_an_assertion_is_allowed(self) -> None:
        before = run.load(VALID)
        after = copy.deepcopy(before)
        after["rationale_summaries"] = after["rationale_summaries"][:1]
        self.assertEqual(repair.subset_violations(before, after), [])


class OneAttemptTests(unittest.TestCase):
    def test_valid_output_is_never_repaired(self) -> None:
        result = repair.run_repair(run.load(VALID), run.load(REPAIRED))
        self.assertEqual(result["outcome"], "valid")
        self.assertEqual(result["attempts"], 0)

    def test_no_corpus_case_takes_more_than_one_attempt(self) -> None:
        for case in corpus_cases():
            self.assertLessEqual(case["expect"]["attempts"], 1, case["id"])

    def test_unrepairable_output_stops_at_one_attempt(self) -> None:
        invalid = run.load(INVALID)
        still_invalid = copy.deepcopy(invalid)
        result = repair.run_repair(invalid, still_invalid)
        self.assertEqual(result["outcome"], "unrepairable")
        self.assertEqual(result["attempts"], 1)
        self.assertTrue(result["errors"])


class CaseWiringTests(unittest.TestCase):
    def test_the_corpus_is_not_empty(self) -> None:
        self.assertGreaterEqual(len(corpus_cases()), 5)

    def test_every_case_pins_the_repair_prompt(self) -> None:
        for case in corpus_cases():
            self.assertEqual(case["prompt"]["path"], "prompts/repair-structured-output.v1.md", case["id"])

    def test_a_mispinned_prompt_version_fails(self) -> None:
        case = run.load("evals/fixtures/repair-wrong-typed-field.case.json")
        case["prompt"] = dict(case["prompt"], version="9.9.9")
        errors = run.evaluate(case)
        self.assertTrue(any("case pins 9.9.9" in error for error in errors), errors)

    def test_the_check_fails_when_the_expectation_is_wrong(self) -> None:
        case = run.load("evals/fixtures/repair-wrong-typed-field.case.json")
        case["expect"] = {"outcome": "refused", "attempts": 1}
        self.assertTrue(run.evaluate(case))


if __name__ == "__main__":
    unittest.main()
