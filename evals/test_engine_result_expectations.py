from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from evals import run
from evals.checks import engine_result


class EngineResultExpectationTests(unittest.TestCase):
    def test_each_optional_negative_expectation_is_observed_failing(self) -> None:
        expected = {
            "selftest-forbidden-proposal-kinds": "forbidden proposal kinds",
            "selftest-forbid-checkpoints": "forbidden checkpoints",
            "selftest-max-abstraction-level": "exceeds maximum",
            "selftest-min-missing-information": "missing information entries",
        }
        paths = run.discover_cases([run.ROOT / "evals" / "selftest"])
        self.assertEqual({json_case_id(path) for path in paths}, set(expected))
        for path in paths:
            case = run.load(path.name, path.parent)
            errors = run.evaluate(case, lambda name, directory=path.parent: run.load(name, directory))
            self.assertTrue(any(expected[case["id"]] in error for error in errors), (case["id"], errors))

    def test_unchanged_reference_fixture_still_passes(self) -> None:
        case = run.load("evals/fixtures/framing-solution-disguised.case.json")
        self.assertEqual(run.evaluate(case), [])

    def test_lateral_level_is_rejected_by_ceiling_comparison(self) -> None:
        case = run.load("evals/fixtures/framing-solution-disguised.case.json")
        artifact = run.load(case["artifact"], run.FIXTURES)
        artifact["proposals"][1]["value"]["levels"] = ["operations"]
        case = copy.deepcopy(case)
        case["expect"]["max_abstraction_level"] = "business"
        errors = run.evaluate(case, lambda _: artifact)
        self.assertTrue(any("non-ladder abstraction level" in error for error in errors), errors)

    def test_non_ladder_frame_level_is_rejected(self) -> None:
        case = run.load("evals/fixtures/framing-solution-disguised.case.json")
        artifact = run.load(case["artifact"], run.FIXTURES)
        artifact["proposals"][2]["value"]["abstraction_level"] = "portfolio"
        case = copy.deepcopy(case)
        case["expect"]["max_abstraction_level"] = "business"
        errors = run.evaluate(case, lambda _: artifact)
        self.assertTrue(any("non-ladder abstraction level" in error for error in errors), errors)

    def test_frame_and_ladder_each_fail_above_ceiling(self) -> None:
        for proposal_index in (1, 2):
            with self.subTest(proposal_index=proposal_index):
                case = run.load("evals/fixtures/framing-solution-disguised.case.json")
                artifact = run.load(case["artifact"], run.FIXTURES)
                artifact["proposals"] = [artifact["proposals"][proposal_index]]
                case["expect"] = {"max_abstraction_level": "system"}
                errors = run.evaluate(case, lambda _: artifact)
                self.assertTrue(any("exceeds maximum" in error for error in errors), errors)
                value = artifact["proposals"][0]["value"]
                if proposal_index == 1:
                    value["levels"] = ["component", "system"]
                else:
                    value["abstraction_level"] = "system"
                self.assertEqual(run.evaluate(case, lambda _: artifact), [])

    def test_invalid_expectation_values_are_named_errors(self) -> None:
        for key, values, fragment in (
            ("forbidden_proposal_kinds", (None, "problem_frame", [{}]), "list of strings"),
            ("forbid_checkpoints", (None, "frame_selection", [42]), "list of strings"),
            ("min_missing_information", (-1, "1", True), "non-negative integer"),
            ("max_abstraction_level", ([], {}, "operations"), "cannot be ranked"),
        ):
            for value in values:
                with self.subTest(key=key, value=value):
                    case = run.load("evals/fixtures/framing-solution-disguised.case.json")
                    case["expect"][key] = value
                    self.assertTrue(any(fragment in error for error in run.evaluate(case)))

    def test_ceiling_requires_comparable_frame_and_ladder_values(self) -> None:
        for proposal in (
            {"kind": "problem_frame", "value": {}},
            {"kind": "problem_frame", "value": {"abstraction_level": []}},
            {"kind": "abstraction_ladder", "value": {}},
            {"kind": "abstraction_ladder", "value": {"levels": [{}]}},
        ):
            with self.subTest(proposal=proposal):
                case = run.load("evals/fixtures/framing-solution-disguised.case.json")
                artifact = run.load(case["artifact"], run.FIXTURES)
                artifact["proposals"] = [proposal]
                case["expect"] = {"max_abstraction_level": "business"}
                self.assertTrue(run.evaluate(case, lambda _: artifact))

    def test_schema_drift_is_reported_by_evaluator(self) -> None:
        case = run.load("evals/fixtures/framing-solution-disguised.case.json")
        schema = copy.deepcopy(engine_result.load_schema("session.schema.json"))
        enum = schema["$defs"]["frame"]["properties"]["abstraction_level"]["enum"]
        enum[:] = [level for level in enum if level != "system"]
        with patch.object(engine_result, "load_schema", return_value=schema):
            self.assertTrue(any("not a subset of session schema enum" in error for error in run.evaluate(case)))

    def test_selftest_cli_reports_the_four_named_failures(self) -> None:
        result = subprocess.run(
            [sys.executable, "evals/run.py", "--root", "evals/selftest", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["passed"], 0)
        self.assertEqual({item["case"] for item in report["results"]}, {
            "selftest-forbidden-proposal-kinds", "selftest-forbid-checkpoints",
            "selftest-max-abstraction-level", "selftest-min-missing-information",
        })
        self.assertTrue(all(item["errors"] for item in report["results"]))

    def test_selftest_wrapper_verifies_expected_failure(self) -> None:
        result = subprocess.run([sys.executable, "evals/selftest.py"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ladder_ordering_is_subset_of_session_schema_enum(self) -> None:
        self.assertTrue(set(engine_result.LADDER_ORDER) <= engine_result._session_abstraction_levels())


def json_case_id(path):
    return run.load(path.name, path.parent)["id"]
