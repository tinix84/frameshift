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
        """Located by JSON path rather than line, since #156 parses these."""
        with PlantedFile("evals/fixtures/_probe.jsonl", '{"thinking": "..."}\n'):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("evals/fixtures/_probe.jsonl", result.stdout)
        self.assertIn("$.thinking", result.stdout)
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

    def test_an_execution_request_is_not_an_engine_result(self) -> None:
        """A request names the engine it is for; only a result carries proposals."""
        content = json.dumps(
            {
                "schema_version": "1.0.0",
                "execution_id": "exec_probe_001",
                "engine": "problem_framing",
                "output_schema": "schemas/engine-result.schema.json",
            },
            indent=2,
        )
        with PlantedFile("evals/fixtures/_probe.request.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_an_execution_envelope_is_not_an_engine_result(self) -> None:
        content = json.dumps(
            {"schema_version": "1.0.0", "execution_id": "exec_probe_001", "stop_reason": "complete"},
            indent=2,
        )
        with PlantedFile("evals/fixtures/_probe.envelope.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

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


class CredentialMaterialCheckTests(unittest.TestCase):
    """#21: no credential material where state is defined or behavior requested."""

    def test_the_repository_is_clean(self) -> None:
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_credential_field_in_a_manifest_fails(self) -> None:
        """Located by JSON path since #158 parses these."""
        content = json.dumps({"schema_version": "1.0.0", "api_key": "redacted"}, indent=2)
        with PlantedFile("adapters/_probe.json", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("$.api_key", result.stdout)
        self.assertIn("api_key", result.stdout)

    def test_a_credential_in_a_prompt_fails(self) -> None:
        """An assignment is material; a sentence about one is not (#158)."""
        content = "# Probe\n\npassword: hunter2\n"
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("password", result.stdout)

    def test_every_declared_term_is_caught(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("v", VALIDATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for term in module.CREDENTIAL_TERMS:
            with self.subTest(term=term):
                with PlantedFile("prompts/_probe.md", f"{term}: some-real-value\n"):
                    result = run_validator()
                self.assertNotEqual(result.returncode, 0, term)

    def test_every_declared_term_is_caught_as_a_key(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("v", VALIDATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for term in module.CREDENTIAL_TERMS:
            with self.subTest(term=term):
                content = json.dumps({term: "some-real-value"}, indent=2)
                with PlantedFile("evals/fixtures/_probe.json", content):
                    result = run_validator()
                self.assertNotEqual(result.returncode, 0, term)

    def test_a_secret_value_is_caught_under_an_innocent_field_name(self) -> None:
        for value in ("-----BEGIN RSA PRIVATE KEY-----", "AKIAIOSFODNN7EXAMPLE", "ghp_abc123"):
            with self.subTest(value=value):
                content = json.dumps({"note": value}, indent=2)
                with PlantedFile("evals/fixtures/_probe.json", content):
                    result = run_validator()
                self.assertNotEqual(result.returncode, 0, value)

    def test_token_counts_is_not_credential_material(self) -> None:
        """The reference checkpoint carries it, and a check that fired here would be turned off."""
        content = json.dumps({"token_counts": {"input": 2810, "output": 640}}, indent=2)
        with PlantedFile("evals/fixtures/_probe.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_credential_owner_field_is_not_credential_material(self) -> None:
        """#21 says a capability declares its credential owner."""
        content = json.dumps({"credential_owner": "workspace", "credentials": "delegated"}, indent=2)
        with PlantedFile("adapters/_probe.json", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_security_docs_may_name_what_they_forbid(self) -> None:
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()
        self.assertTrue("secret" in security or "credential" in security)
        self.assertTrue("secret" in contributing or "credential" in contributing)


def validator_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_repo", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def story(number, labels, milestone="M0"):
    return {
        "number": number,
        "labels": [{"name": name} for name in labels],
        "milestone": {"title": milestone} if milestone else None,
    }


class StoryPlacementTests(unittest.TestCase):
    """The rule is pure over the issue list; `gh` is the caller's problem."""

    def setUp(self):
        self.module = validator_module()
        self.columns = self.module.backbone_columns()

    def test_the_map_declares_nine_columns(self):
        self.assertEqual(len(self.columns), 9)
        self.assertIn("column:reframe", self.columns)

    def test_the_declared_columns_are_unique(self):
        self.assertEqual(len(set(self.columns)), len(self.columns))

    def test_a_correctly_placed_story_passes(self):
        issues = [story(1, ["story", "column:reframe"])]
        self.assertEqual(self.module.story_placement_errors(issues, self.columns), [])

    def test_a_story_with_no_column_fails(self):
        issues = [story(2, ["story"])]
        errors = self.module.story_placement_errors(issues, self.columns)
        self.assertTrue(any("0 journey-position labels" in item for item in errors), errors)

    def test_a_story_in_two_columns_fails(self):
        issues = [story(3, ["story", "column:reframe", "column:decide"])]
        errors = self.module.story_placement_errors(issues, self.columns)
        self.assertTrue(any("2 journey-position labels" in item for item in errors), errors)

    def test_a_story_with_no_milestone_fails(self):
        issues = [story(4, ["story", "column:carry"], milestone=None)]
        errors = self.module.story_placement_errors(issues, self.columns)
        self.assertTrue(any("no milestone" in item for item in errors), errors)

    def test_an_unknown_column_label_fails(self):
        issues = [story(5, ["story", "column:invented"])]
        errors = self.module.story_placement_errors(issues, self.columns)
        self.assertTrue(any("unknown column labels" in item for item in errors), errors)

    def test_every_declared_column_is_accepted(self):
        for column in self.columns:
            with self.subTest(column=column):
                issues = [story(6, ["story", column])]
                self.assertEqual(self.module.story_placement_errors(issues, self.columns), [])

    def test_the_check_never_passes_silently(self):
        """Either it examined issues or it said why it could not — never nothing.

        CI runs with `gh` unauthenticated, so the skip branch is the one
        exercised there; a developer machine takes the other. Both must speak.
        """
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            "story placement checked over" in result.stdout
            or "skipping the story placement check" in result.stdout,
            result.stdout,
        )


class SentenceScopeTests(unittest.TestCase):
    """A marker exempts a term in its own sentence, not anywhere on the line."""

    def setUp(self):
        self.module = validator_module()

    def test_a_marker_in_an_unrelated_sentence_does_not_exempt(self):
        """The shape #100 still allowed: one line, two sentences, one prohibition."""
        content = "# Probe" + chr(10) * 2 + "Never skip the intake step. Work through the analysis step by step." + chr(10)
        with PlantedFile("prompts/_probe.v1.md", content):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("step by step", result.stdout.lower())

    def test_a_marker_in_the_same_sentence_still_exempts(self):
        content = "# Probe" + chr(10) * 2 + "Never expose private chain-of-thought." + chr(10)
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_comma_keeps_one_sentence_together(self):
        content = "# Probe" + chr(10) * 2 + "The engine must not be asked to reason step by step, ever." + chr(10)
        with PlantedFile("prompts/_probe.md", content):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_committed_prompt_earns_its_own_marker(self):
        """It used to pass on a `never` 380 characters away."""
        text = (ROOT / "prompts" / "problem-framing.v1.md").read_text(encoding="utf-8")
        for sentence in self.module.sentences(text):
            if "chain-of-thought" in sentence.lower():
                self.assertIn("never", sentence.lower())


class SentenceSplitterTests(unittest.TestCase):
    def setUp(self):
        self.split = validator_module().sentences

    def test_two_sentences_split(self):
        self.assertEqual(len(self.split("One thing. Another thing.")), 2)

    def test_an_abbreviation_does_not_split(self):
        self.assertEqual(len(self.split("Use a marker, e.g. never, in the sentence.")), 1)

    def test_a_decimal_number_does_not_split(self):
        self.assertEqual(len(self.split("The budget is 2.5 seconds of latency.")), 1)

    def test_a_line_with_no_punctuation_is_one_sentence(self):
        self.assertEqual(self.split("| a | b |"), ["| a | b |"])

    def test_an_abbreviation_keeps_its_dots(self):
        self.assertIn("e.g.", self.split("See e.g. the notes.")[0])

    def test_blank_pieces_are_dropped(self):
        self.assertEqual(self.split("One.    Two."), ["One.", "Two."])

class KeyVersusValueScanTests(unittest.TestCase):
    """Keys get substrings, values get words (#156)."""

    def plant(self, document, minified=False):
        separators = (",", ":") if minified else None
        content = json.dumps(document, separators=separators, indent=None if minified else 2)
        with PlantedFile("evals/fixtures/_probe.json", content):
            return run_validator()

    def statement(self, text):
        return {"statements": [{"id": "stmt_probe", "text": text}]}

    def test_ordinary_prose_containing_thinking_passes(self):
        result = self.plant(self.statement("Our thinking has changed since the pack review."))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_forbidden_word_inside_a_longer_word_passes(self):
        """This is a reframing tool; its own exemplars could say this."""
        result = self.plant(self.statement("Rethinking the frame is the point."))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_ordinary_prose_containing_thoughts_passes(self):
        result = self.plant(self.statement("Second thoughts about the supplier."))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_forbidden_key_fails_with_its_json_path(self):
        result = self.plant({"a": [{"model_thoughts": "x"}]})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("$.a[0].model_thoughts", result.stdout)

    def test_a_hyphenated_key_is_normalized(self):
        result = self.plant({"chain-of-thought": "x"})
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_a_key_in_a_minified_file_is_still_found(self):
        """The old line scan reported every violation at line 1."""
        result = self.plant({"deep": {"inner": {"scratchpad": 1}}}, minified=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("$.deep.inner.scratchpad", result.stdout)

    def test_a_value_that_names_a_forbidden_term_still_fails(self):
        result = self.plant({"note": "chain_of_thought"})
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_a_value_asking_for_reasoning_still_fails(self):
        result = self.plant({"note": "show your reasoning in full"})
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_a_yaml_key_still_fails_after_the_split(self):
        with PlantedFile("adapters/_probe.yml", "steps:" + chr(10) + "  - name: model_thoughts" + chr(10)):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_a_yaml_line_with_a_longer_word_passes(self):
        with PlantedFile("adapters/_probe.yml", "note: rethinking the frame" + chr(10)):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_an_unparseable_fixture_is_reported_once(self):
        """`main` already reports invalid JSON; failing twice would obscure it."""
        with PlantedFile("evals/fixtures/_probe.json", "{not json"):
            result = run_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("invalid JSON", result.stdout)

class CredentialScopeTests(unittest.TestCase):
    """A term must denote the material, not the topic (#158)."""

    def plant_json(self, document):
        with PlantedFile("evals/fixtures/_probe.json", json.dumps(document, indent=2)):
            return run_validator()

    def test_a_policy_key_is_about_credentials_not_one(self):
        for key in ("password_policy", "api_key_rotation", "credential_owner", "token_counts"):
            with self.subTest(key=key):
                result = self.plant_json({key: "quarterly"})
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_key_naming_what_it_holds_fails(self):
        for key in ("password", "user_password", "api_key", "client_api_key"):
            with self.subTest(key=key):
                result = self.plant_json({key: "hunter2"})
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_prose_about_credentials_passes(self):
        for note in ("Rotate the password quarterly.", "Document the api_key rotation schedule."):
            with self.subTest(note=note):
                result = self.plant_json({"note": note})
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_prose_about_credentials_passes_in_a_prompt(self):
        with PlantedFile("prompts/_probe.md", "# P" + chr(10) * 2 + "Rotate the password quarterly." + chr(10)):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_secret_value_is_caught_under_any_key(self):
        for value in ("-----BEGIN RSA PRIVATE KEY-----", "AKIAIOSFODNN7EXAMPLE", "ghp_abc123", "xoxb-1-2"):
            with self.subTest(value=value):
                result = self.plant_json({"note": value})
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_a_yaml_assignment_fails_and_a_policy_key_does_not(self):
        with PlantedFile("adapters/_probe.yml", "password: hunter2" + chr(10)):
            self.assertNotEqual(run_validator().returncode, 0)
        with PlantedFile("adapters/_probe.yml", "password_policy: quarterly" + chr(10)):
            result = run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_nested_credential_key_is_found_by_path(self):
        result = self.plant_json({"adapter": {"auth": {"client_secret": "x"}}})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("$.adapter.auth.client_secret", result.stdout)

class LabelRegistryTests(unittest.TestCase):
    """The tracker's column labels are the map's, exactly."""

    def setUp(self):
        self.module = validator_module()
        self.columns = self.module.backbone_columns()

    def test_the_declared_labels_and_the_story_label_are_enough(self):
        labels = list(self.columns) + ["story", "P1", "documentation"]
        self.assertEqual(self.module.label_registry_errors(labels, self.columns), [])

    def test_a_label_the_map_declares_but_the_tracker_lacks_fails(self):
        labels = list(self.columns)[1:] + ["story"]
        errors = self.module.label_registry_errors(labels, self.columns)
        self.assertTrue(any("does not exist on the tracker" in item for item in errors), errors)

    def test_a_label_the_tracker_has_but_the_map_lacks_fails(self):
        labels = list(self.columns) + ["story", "column:invented"]
        errors = self.module.label_registry_errors(labels, self.columns)
        self.assertTrue(any("column:invented" in item for item in errors), errors)

    def test_a_renamed_label_reports_both_halves(self):
        """The drift a rename causes, which nothing noticed before."""
        labels = [name for name in self.columns if name != "column:reframe"]
        labels += ["column:reframed", "story"]
        errors = self.module.label_registry_errors(labels, self.columns)
        self.assertTrue(
            any("declares column:reframe," in item for item in errors), errors
        )
        self.assertTrue(
            any("has column:reframed," in item for item in errors), errors
        )

    def test_a_missing_story_label_fails(self):
        errors = self.module.label_registry_errors(list(self.columns), self.columns)
        self.assertTrue(any("`story` label does not exist" in item for item in errors), errors)

    def test_the_live_tracker_agrees_with_the_map(self):
        """Runs only where gh can answer; CI takes the skip branch."""
        labels = self.module.fetch_labels()
        if labels is None:
            self.skipTest("gh is unavailable")
        self.assertEqual(self.module.label_registry_errors(labels, self.columns), [])

if __name__ == "__main__":
    unittest.main()
