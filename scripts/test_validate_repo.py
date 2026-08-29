#!/usr/bin/env python3
"""Tests for the repository validator.

A checker that silently matches nothing is worse than no checker, because it
manufactures confidence. These tests plant a violation and assert the validator
notices it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_repo.py"


def run_validator() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class PlantedFile:
    """Write a file into the repository for the duration of one assertion."""

    def __init__(self, relative: str, content: str) -> None:
        self.path = ROOT / relative
        self.content = content

    def __enter__(self) -> Path:
        self.path.write_text(self.content, encoding="utf-8")
        return self.path

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


class ChainOfThoughtCheckTests(unittest.TestCase):
    def test_clean_repository_passes(self) -> None:
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_forbidden_field_term_in_a_schema_fails(self) -> None:
        content = json.dumps({"properties": {"reasoning_trace": {"type": "string"}}}, indent=2)
        with PlantedFile("schemas/_probe.schema.json", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schemas/_probe.schema.json", result.stdout)
        self.assertIn("reasoning_trace", result.stdout)

    def test_forbidden_term_in_a_fixture_fails(self) -> None:
        content = json.dumps({"scratchpad": "..."}, indent=2)
        with PlantedFile("evals/fixtures/_probe.json", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scratchpad", result.stdout)

    def test_forbidden_term_in_an_adapter_fails(self) -> None:
        with PlantedFile("adapters/_probe.md", "Record the model's inner monologue.\n"):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inner monologue", result.stdout)

    def test_prompt_asking_for_reasoning_fails_with_file_line_and_term(self) -> None:
        content = "# Probe\n\nExplain the answer.\nWork through it step by step.\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prompts/_probe.md:4", result.stdout)
        self.assertIn("step by step", result.stdout)

    def test_stating_the_prohibition_is_allowed(self) -> None:
        content = "# Probe\n\nDo not reason step by step in the output.\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_prohibition_heading_covers_its_section(self) -> None:
        content = "# Probe\n\n## Non-goals\n\n- Exposing private chain of thought.\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_exempt_paths_may_name_the_prohibition(self) -> None:
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)
        adr = (ROOT / "docs" / "adr" / "0007-no-chain-of-thought-persistence.md").read_text(encoding="utf-8")
        self.assertIn("chain-of-thought", adr.lower())


class RationaleSummaryCheckTests(unittest.TestCase):
    def test_engine_result_without_rationale_summaries_fails(self) -> None:
        content = json.dumps({"schema_version": "1.0.0", "engine": "problem_framing", "rationale_summaries": []}, indent=2)
        with PlantedFile("evals/fixtures/_probe.result.json", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without rationale summaries", result.stdout)

    def test_engine_result_with_rationale_summaries_passes(self) -> None:
        content = json.dumps({"schema_version": "1.0.0", "engine": "problem_framing", "rationale_summaries": ["A summary."]}, indent=2)
        with PlantedFile("evals/fixtures/_probe.result.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
