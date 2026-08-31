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
        content = "# Probe\n\nNever ask the model to reason step by step in the output.\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_every_marker_exempts_a_line_that_states_the_prohibition(self) -> None:
        for sentence in (
            "The output must not carry chain of thought.",
            "Exposing a scratchpad is forbidden.",
            "This prompt prohibits any request to show your reasoning.",
            "Non-goal: recording your thinking.",
            "Carry a rationale summary instead of an inner monologue.",
            "Summarize the conclusion rather than reasoning step by step.",
        ):
            with self.subTest(sentence=sentence):
                with PlantedFile("prompts/_probe.md", f"# Probe\n\n{sentence}\n"):
                    result = run_validator()
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_nearby_negation_does_not_silence_the_term(self) -> None:
        content = "# Probe\n\nWork through the analysis step by step, but do not stop early.\n"
        with PlantedFile("prompts/_probe.v1.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("prompts/_probe.v1.md:3", result.stdout)
        self.assertIn("step by step", result.stdout)

    def test_a_bare_request_for_reasoning_fails(self) -> None:
        content = "# Probe\n\nWork through the analysis step by step.\n"
        with PlantedFile("prompts/_probe.v1.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("step by step", result.stdout)

    def test_a_prohibition_heading_does_not_cover_its_section(self) -> None:
        content = "# Probe\n\n## Notes on what is not required\n\nShow your reasoning in full.\n"
        with PlantedFile("prompts/_probe.v1.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("prompts/_probe.v1.md:5", result.stdout)
        self.assertIn("show your reasoning", result.stdout.lower())

    def test_a_heading_exempts_only_its_own_line(self) -> None:
        content = "# Probe\n\n## Never expose chain of thought\n\nThe engine emits a rationale summary.\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_forbidden_field_term_in_a_yaml_file_fails(self) -> None:
        # `thoughts` is a field term and not a prose term, so only the machine-
        # readable pass can catch it — which is the point of the case.
        with PlantedFile("adapters/_probe.yml", "steps:\n  - name: model_thoughts\n"):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("adapters/_probe.yml:2", result.stdout)
        self.assertIn("thoughts", result.stdout)

    def test_forbidden_field_term_in_a_jsonl_file_fails(self) -> None:
        with PlantedFile("evals/fixtures/_probe.jsonl", '{"thinking": "..."}\n'):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("evals/fixtures/_probe.jsonl:1", result.stdout)
        self.assertIn("thinking", result.stdout)

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

    def test_engine_result_without_a_named_engine_fails(self) -> None:
        content = json.dumps(
            {
                "schema_version": "1.0.0",
                "execution_id": "exec_probe_001",
                "proposals": [],
                "rationale_summaries": ["A summary."],
            },
            indent=2,
        )
        with PlantedFile("evals/fixtures/_probe.result.json", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("without a named engine", result.stdout)

    def test_engine_result_with_rationale_summaries_passes(self) -> None:
        content = json.dumps({"schema_version": "1.0.0", "engine": "problem_framing", "rationale_summaries": ["A summary."]}, indent=2)
        with PlantedFile("evals/fixtures/_probe.result.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)


class StoryMapCheckTests(unittest.TestCase):
    """A map that names an exemplar nobody can run is the failure being caught."""

    MAP = ROOT / "docs" / "story-map.md"

    def setUp(self) -> None:
        self.original = self.MAP.read_bytes()

    def tearDown(self) -> None:
        self.MAP.write_bytes(self.original)

    def rewrite(self, text: str) -> None:
        self.MAP.write_text(text, encoding="utf-8", newline="")

    def text(self) -> str:
        return self.original.decode("utf-8")

    def test_the_committed_map_passes(self) -> None:
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_both_committed_exemplars_have_a_fixture(self) -> None:
        for name in ("battery-single-source", "kafka-in-disguise"):
            with self.subTest(exemplar=name):
                self.assertIn(f"`{name}`", self.text())
                self.assertTrue(
                    list((ROOT / "evals" / "fixtures").glob(f"{name}.*")), name
                )

    def test_an_exemplar_without_a_fixture_fails(self) -> None:
        self.rewrite(self.text().replace(
            "| `kafka-in-disguise` |", "| `nobody-can-run-this` |", 1))
        result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("nobody-can-run-this", result.stdout)
        self.assertIn("has no fixture", result.stdout)

    def test_a_map_without_a_north_star_fails(self) -> None:
        self.rewrite(self.text().replace("## North Star", "## Vision", 1))
        result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("North Star", result.stdout)

    def test_a_map_without_an_exemplars_section_fails(self) -> None:
        self.rewrite(self.text().replace("## Exemplars", "## Examples", 1))
        result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Exemplars", result.stdout)

    def test_a_backbone_with_no_columns_fails(self) -> None:
        text = self.text()
        backbone = text.partition("## The backbone")[2].partition("## Slices")[0]
        prose = "\n\nThe journey, described in prose.\n\n"
        self.rewrite(text.replace(backbone, prose, 1))
        result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("no columns", result.stdout)

    def test_a_missing_map_fails(self) -> None:
        self.MAP.unlink()
        result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("docs/story-map.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
