#!/usr/bin/env python3
"""Tests that the conformance report distinguishes the cases that matter.

The report exists so an adapter author can tell three states apart that a flat
per-fixture pass list conflates: conformant, nonconformant with the cases named,
and never exercised at all.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import adapter, schema  # noqa: E402

CASE = "evals/fixtures/adapter-conformance-report.case.json"


def build(transports: list[str], corpus: set[str] | None = None) -> dict:
    declared = set(run.load(CASE)["corpus"]) if corpus is None else corpus
    return adapter.conformance_report(lambda name: run.load(name, run.FIXTURES), transports, declared)


def verdicts(report: dict) -> dict[str, str]:
    return {item["name"]: item["outcome"] for item in report["adapters"]}


class ReportShapeTests(unittest.TestCase):
    def test_the_declared_case_passes(self) -> None:
        self.assertEqual(run.evaluate(run.load(CASE)), [])

    def test_the_report_validates_against_its_committed_schema(self) -> None:
        report = build(["echo", "reordering"])
        errors = schema.validate(
            report, schema.load_schema(adapter.REPORT_SCHEMA), current=adapter.REPORT_SCHEMA
        )
        self.assertEqual(errors, [])

    def test_a_leaky_adapters_report_also_validates(self) -> None:
        report = build(["echo", "request_id_promoting"])
        errors = schema.validate(
            report, schema.load_schema(adapter.REPORT_SCHEMA), current=adapter.REPORT_SCHEMA
        )
        self.assertEqual(errors, [])

    def test_every_registered_adapter_appears(self) -> None:
        report = build(["echo"])
        self.assertEqual(set(verdicts(report)), set(adapter.ADAPTERS))


class VerdictTests(unittest.TestCase):
    def test_a_neutral_adapter_is_conformant(self) -> None:
        self.assertEqual(verdicts(build(["echo", "reordering", "crlf_text"]))["reordering"], "conformant")

    def test_a_leaky_adapter_is_nonconformant(self) -> None:
        self.assertEqual(verdicts(build(["echo", "request_id_promoting"]))["request_id_promoting"], "nonconformant")

    def test_an_unexercised_adapter_is_uncovered_and_not_conformant(self) -> None:
        """The distinction the flat pass list could not make."""
        report = build(["echo"])
        self.assertEqual(verdicts(report)["request_id_promoting"], "uncovered")
        self.assertNotEqual(verdicts(report)["request_id_promoting"], "conformant")

    def test_an_empty_corpus_leaves_every_adapter_uncovered(self) -> None:
        report = build(["echo", "reordering"], corpus=set())
        self.assertEqual(set(verdicts(report).values()), {"uncovered"})

    def test_an_uncovered_adapter_carries_no_checks(self) -> None:
        report = build(["echo"])
        unexercised = next(item for item in report["adapters"] if item["name"] == "crlf_text")
        self.assertEqual(unexercised["checks"], [])


class DetailTests(unittest.TestCase):
    def test_a_failing_adapter_names_every_case_it_broke(self) -> None:
        report = build(["echo", "request_id_promoting"])
        leaky = next(item for item in report["adapters"] if item["name"] == "request_id_promoting")
        failed = [
            case["id"]
            for check in leaky["checks"]
            for case in check["cases"]
            if case["outcome"] == "fail"
        ]
        self.assertTrue(failed, "a nonconformant adapter must name the cases it broke")
        for check in leaky["checks"]:
            for case in check["cases"]:
                if case["outcome"] == "fail":
                    self.assertTrue(case["violations"], case["id"])

    def test_a_check_is_nonconformant_only_if_one_of_its_cases_failed(self) -> None:
        report = build(["echo", "request_id_promoting"])
        for item in report["adapters"]:
            for check in item["checks"]:
                failed = any(case["outcome"] == "fail" for case in check["cases"])
                expected = "nonconformant" if failed else "conformant"
                self.assertEqual(check["outcome"], expected, (item["name"], check["name"]))

    def test_a_passing_case_carries_no_violations_key(self) -> None:
        report = build(["echo"])
        for check in report["adapters"][1]["checks"]:
            for case in check["cases"]:
                if case["outcome"] == "pass":
                    self.assertNotIn("violations", case)


class CaseWiringTests(unittest.TestCase):
    def test_a_wrong_expected_verdict_fails_the_case(self) -> None:
        case = run.load(CASE)
        case["expect"] = dict(case["expect"], nonconformant=["echo"])
        errors = run.evaluate(case)
        self.assertTrue(any("echo is conformant" in item for item in errors), errors)

    def test_run_json_output_is_unchanged_in_shape(self) -> None:
        """Existing consumers of the harness report are unaffected."""
        import json
        import subprocess

        result = subprocess.run(
            [sys.executable, "evals/run.py", "--json"],
            cwd=run.ROOT, capture_output=True, text=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"passed", "total", "results"})
        self.assertEqual(set(report["results"][0]), {"case", "passed", "errors"})


class EmittedReportTests(unittest.TestCase):
    """The report reaches an adapter author (#114).

    `conformance_report` built the matrix and validated its shape, and then
    nothing printed it: `run.py` knew only `PASS adapter-conformance-report`.
    """

    def test_the_rendering_names_every_adapter_check_and_verdict(self) -> None:
        text = adapter.render_conformance(build(["echo", "crlf_text"]))
        self.assertIn("echo: conformant", text)
        self.assertIn("crlf_text: conformant", text)
        self.assertIn("extension_annotating: uncovered", text)
        self.assertIn("request_id_promoting: uncovered", text)
        for check in run.load(CASE)["corpus"]:
            self.assertIn(f"  {check}: conformant", text)

    def test_the_rendering_of_a_failure_names_the_case_and_the_violation(self) -> None:
        text = adapter.render_conformance(build(["request_id_promoting"]))
        self.assertIn("request_id_promoting: nonconformant", text)
        self.assertIn("engine_result_repair: nonconformant", text)
        self.assertIn("    - repair-wrong-typed-field", text)
        self.assertIn("outcome is unrepairable, case expects repaired", text)

    def test_the_conformance_flag_emits_the_matrix_beside_the_results(self) -> None:
        import json
        import subprocess

        result = subprocess.run(
            [sys.executable, "evals/run.py", "--json", "--conformance"],
            cwd=run.ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"passed", "total", "results", "conformance"})
        matrix = report["conformance"]["adapter-conformance-report"]
        self.assertEqual(
            verdicts(matrix),
            {
                "crlf_text": "conformant",
                "echo": "conformant",
                "extension_annotating": "uncovered",
                "reordering": "conformant",
                "request_id_promoting": "uncovered",
            },
        )
        conformant = next(item for item in matrix["adapters"] if item["name"] == "echo")
        self.assertEqual({item["name"] for item in conformant["checks"]}, set(run.load(CASE)["corpus"]))

    def test_the_human_rendering_is_printed_with_the_flag(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "evals/run.py", "--conformance", "--root", "evals/fixtures"],
            cwd=run.ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        self.assertIn("Adapter conformance (adapter-conformance-report)", result.stdout)
        self.assertIn("echo: conformant", result.stdout)
        self.assertIn("extension_annotating: uncovered", result.stdout)


if __name__ == "__main__":
    unittest.main()
