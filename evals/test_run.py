#!/usr/bin/env python3
"""Tests for the harness dispatch seam itself."""

from __future__ import annotations

import sys
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import REGISTRY  # noqa: E402


class DispatchTests(unittest.TestCase):
    def test_unknown_check_is_a_named_error(self) -> None:
        errors = run.evaluate({"id": "x", "check": "no_such_check"})
        self.assertEqual(len(errors), 1)
        self.assertIn("unknown check: no_such_check", errors[0])

    def test_missing_check_is_a_named_error(self) -> None:
        errors = run.evaluate({"id": "x"})
        self.assertEqual(len(errors), 1)
        self.assertIn("declares no check", errors[0])

    def test_every_fixture_declares_a_registered_check(self) -> None:
        for path in sorted(run.FIXTURES.glob("*.case.json")):
            case = run.load(str(path.relative_to(run.ROOT)))
            self.assertIn(case.get("check"), REGISTRY, path.name)

    def test_discovery_includes_the_corpus_and_case_relative_artifacts(self) -> None:
        paths = run.discover_cases([run.FIXTURES, run.CORPUS])
        corpus_case = next(path for path in paths if path.parent.name == "kafka-in-disguise")
        case = json.loads(corpus_case.read_text(encoding="utf-8"))
        errors = run.evaluate(case, lambda name: run.load(name, corpus_case.parent))
        self.assertEqual(errors, [])

    def test_corpus_directory_can_move_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "case"
            shutil.copytree(run.CORPUS / "kafka-in-disguise", copied)
            paths = run.discover_cases([copied])
            case_path = paths[0]
            case = json.loads(case_path.read_text(encoding="utf-8"))
            self.assertEqual(run.evaluate(case, lambda name: run.load(name, case_path.parent)), [])

    def test_duplicate_case_ids_name_both_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("one", "two"):
                directory = root / name
                directory.mkdir()
                (directory / "case.case.json").write_text(
                    json.dumps({"id": "same", "check": "engine_result_invariants", "artifact": "missing.json", "expect": {}}),
                    encoding="utf-8",
                )
            with self.assertRaises(ValueError) as context:
                run.discover_cases([root])
            self.assertIn("same", str(context.exception))
            self.assertIn("one", str(context.exception))
            self.assertIn("two", str(context.exception))

    def test_corpus_rejects_malformed_supporting_documents(self) -> None:
        case = json.loads((run.CORPUS / "kafka-in-disguise" / "kafka-in-disguise.case.json").read_text())
        directory = run.CORPUS / "kafka-in-disguise"
        def loader(name):
            if name == "citation.json": return []
            if name == "intake.json": return {"bad": True}
            return run.load(name, directory)
        errors = run.evaluate(case, loader)
        self.assertTrue(any("citation must be an object" in item for item in errors))

    def test_corpus_rejects_each_malformed_citation_field(self) -> None:
        case = json.loads((run.CORPUS / "kafka-in-disguise" / "kafka-in-disguise.case.json").read_text())
        directory = run.CORPUS / "kafka-in-disguise"
        citation = json.loads((directory / "citation.json").read_text())
        faults = {
            "relationship": "copied_from",
            "title": "",
            "source_url": "not a url",
            "access_date": "yesterday",
        }
        for field, value in faults.items():
            with self.subTest(field=field):
                mutated = dict(citation, **{field: value})
                errors = run.evaluate(
                    case,
                    lambda name, mutated=mutated: mutated
                    if name == "citation.json"
                    else run.load(name, directory),
                )
                expected = {
                    "relationship": "citation relationship must be inspired_by",
                    "title": "citation missing non-empty title",
                    "source_url": "citation source_url must be an HTTP or HTTPS URL",
                    "access_date": "citation access_date must be an ISO date",
                }[field]
                self.assertIn(expected, errors)

    def test_corpus_rejects_a_malformed_canonical_intake(self) -> None:
        case = json.loads((run.CORPUS / "kafka-in-disguise" / "kafka-in-disguise.case.json").read_text())
        directory = run.CORPUS / "kafka-in-disguise"
        intake = json.loads((directory / "intake.json").read_text())
        intake["primary_role"] = "not-a-role"
        errors = run.evaluate(
            case,
            lambda name: intake if name == "intake.json" else run.load(name, directory),
        )
        self.assertTrue(any("intake violates session statement schema" in item for item in errors), errors)

    def test_corpus_reports_schema_failure_for_null_proposals(self) -> None:
        case = json.loads((run.CORPUS / "kafka-in-disguise" / "kafka-in-disguise.case.json").read_text())
        directory = run.CORPUS / "kafka-in-disguise"
        result = json.loads((directory / "reference.result.json").read_text())
        result["proposals"] = None
        errors = run.evaluate(
            case,
            lambda name: result if name == case["artifact"] else run.load(name, directory),
        )
        self.assertTrue(any("reference result violates engine-result schema" in item for item in errors), errors)

    def test_case_loader_does_not_escape_to_repository(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run.load("schemas/local.json", run.CORPUS / "kafka-in-disguise")

    def test_case_loader_reads_local_schema_without_prefix_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "schemas").mkdir()
            expected = {"type": "object", "title": "local"}
            (directory / "schemas" / "local.json").write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(run.load("schemas/local.json", directory), expected)

    def test_relocated_cli_runs_from_an_unrelated_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied = root / "copied-case"
            shutil.copytree(run.CORPUS / "kafka-in-disguise", copied)
            unrelated = root / "unrelated"
            unrelated.mkdir()
            completed = subprocess.run(
                [sys.executable, str(run.__file__), "--root", str(copied), "--json"],
                cwd=unrelated,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["total"], 1)
            self.assertEqual(report["passed"], 1)

    def test_headphones_case_does_not_propose_a_problem_frame(self) -> None:
        case_dir = run.CORPUS / "headphones-for-everyone"
        result = json.loads((case_dir / "reference.result.json").read_text(encoding="utf-8"))
        kinds = {proposal.get("kind") for proposal in result["proposals"]}
        self.assertNotIn("problem_frame", kinds)


if __name__ == "__main__":
    unittest.main()
