#!/usr/bin/env python3
"""Tests for the harness dispatch seam itself."""

from __future__ import annotations

import sys
import json
import shutil
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

    def test_case_loader_does_not_escape_to_repository(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run.load("schemas/local.json", run.CORPUS / "kafka-in-disguise")


if __name__ == "__main__":
    unittest.main()
