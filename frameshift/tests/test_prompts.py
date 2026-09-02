#!/usr/bin/env python3
"""Tests for prompt manifests.

A prompt that declares an output schema and an evaluation fixture is making a
promise. These prove the promise is checked: that a reference which does not
resolve fails, that a duplicate id fails, and that the parser reports what it
cannot read rather than skipping it.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.validation import prompts  # noqa: E402


class PlantedPrompt:
    """A prompt file that exists for the duration of one assertion."""

    def __init__(self, name: str, text: str) -> None:
        self.path = prompts.PROMPTS / name
        self.text = text

    def __enter__(self) -> Path:
        self.path.write_text(self.text, encoding="utf-8", newline="")
        return self.path

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


BODY = "\nDo the thing.\n"


def probe(extra: str = "", body: str = BODY, identifier: str = "frameshift.probe.v1") -> str:
    """A valid prompt file, with a body digest that actually matches its body."""
    front = f"---\nid: {identifier}\nversion: 1.0.0\nengine: shared\n"
    if extra:
        front += extra + "\n"
    placeholder = front + "body_digest: sha256:" + "0" * 64 + "\n---\n" + body
    digest = prompts.body_digest(placeholder)
    return front + f"body_digest: {digest}\n---\n" + body


VALID = probe()


class ParserTests(unittest.TestCase):
    def test_a_scalar_and_a_list_are_both_read(self) -> None:
        manifest = prompts.parse_front_matter(
            "---\nid: a.b.c\nversion: 1.0.0\nengine: shared\nfixtures: [one, two]\n---\n\nbody\n"
        )
        self.assertEqual(manifest["fixtures"], ["one", "two"])
        self.assertEqual(manifest["version"], "1.0.0")

    def test_an_empty_list_is_read_as_empty(self) -> None:
        manifest = prompts.parse_front_matter(
            "---\nid: a.b.c\nversion: 1.0.0\nengine: shared\nfixtures: []\n---\n\nbody\n"
        )
        self.assertEqual(manifest["fixtures"], [])

    def test_a_missing_block_is_reported(self) -> None:
        with self.assertRaises(prompts.MalformedFrontMatter):
            prompts.parse_front_matter("No front matter here.\n")

    def test_a_shape_outside_the_subset_is_reported_not_skipped(self) -> None:
        """A field nobody can parse must not slip past as absent."""
        with self.assertRaises(prompts.MalformedFrontMatter):
            prompts.parse_front_matter(
                "---\nid: a.b.c\nversion: 1.0.0\nengine: shared\nnested:\n  - deep\n---\n\nbody\n"
            )

    def test_every_committed_prompt_parses(self) -> None:
        paths = sorted(prompts.PROMPTS.glob("*.md"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(prompt=path.name):
                manifest = prompts.parse_front_matter(path.read_text(encoding="utf-8"))
                self.assertIn("id", manifest)


class ManifestTests(unittest.TestCase):
    def test_the_committed_prompts_are_clean(self) -> None:
        self.assertEqual(prompts.prompt_manifest_violations(), [])

    def test_a_missing_required_field_fails(self) -> None:
        with PlantedPrompt("_probe.md", "---\nid: frameshift.probe.v1\nversion: 1.0.0\n---\n\nbody\n"):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("engine" in item for item in violations), violations)

    def test_an_unknown_engine_fails(self) -> None:
        text = VALID.replace("engine: shared", "engine: telepathy")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("telepathy" in item for item in violations), violations)

    def test_a_malformed_version_fails(self) -> None:
        text = VALID.replace("version: 1.0.0", "version: one")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(violations)

    def test_an_output_schema_that_does_not_exist_fails(self) -> None:
        text = VALID.replace("engine: shared", "engine: shared\noutput_schema: schemas/nope.json")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("does not exist" in item for item in violations), violations)

    def test_a_fixture_that_does_not_exist_fails(self) -> None:
        text = VALID.replace("engine: shared", "engine: shared\nfixtures: [not-a-case]")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("not-a-case" in item for item in violations), violations)

    def test_a_repair_prompt_naming_nothing_fails(self) -> None:
        text = VALID.replace("engine: shared", "engine: shared\nrepair_prompt: frameshift.absent.v1")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("names no committed prompt" in item for item in violations), violations)

    def test_a_duplicate_id_fails(self) -> None:
        text = VALID.replace("frameshift.probe.v1", "frameshift.problem-framing.v1")
        with PlantedPrompt("_probe.md", text):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(any("already declared" in item for item in violations), violations)

    def test_the_framing_prompt_names_its_repair_prompt(self) -> None:
        manifest = prompts.parse_front_matter(
            (prompts.PROMPTS / "problem-framing.v1.md").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["repair_prompt"], "frameshift.repair-structured-output.v1")

    def test_a_body_that_changed_without_the_version_is_caught(self) -> None:
        """#20's versioning rule: a prompt cannot change under a fixed version."""
        edited = probe().replace("Do the thing.", "Do something materially different.")
        with PlantedPrompt("_probe.md", edited):
            violations = prompts.prompt_manifest_violations()
        self.assertTrue(
            any("the body changed without the version changing" in item for item in violations),
            violations,
        )

    def test_every_committed_prompt_declares_a_matching_digest(self) -> None:
        for path in sorted(prompts.PROMPTS.glob("*.md")):
            with self.subTest(prompt=path.name):
                text = path.read_text(encoding="utf-8")
                manifest = prompts.parse_front_matter(text)
                self.assertEqual(manifest["body_digest"], prompts.body_digest(text))

    def test_the_digest_covers_the_body_and_not_the_manifest(self) -> None:
        """Adding a manifest field must not change the digest, or nothing could be added."""
        plain = probe()
        annotated = probe(extra="repair_prompt: frameshift.repair-structured-output.v1")
        self.assertEqual(prompts.body_digest(plain), prompts.body_digest(annotated))

    def test_the_digest_ignores_line_endings(self) -> None:
        self.assertEqual(prompts.body_digest(probe()), prompts.body_digest(probe().replace("\n", "\r\n")))

    def test_the_planted_file_is_always_removed(self) -> None:
        with PlantedPrompt("_probe.md", VALID) as path:
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())


class FlowListTests(unittest.TestCase):
    """An item containing a comma must survive, or the manifest lies."""

    def test_a_quoted_item_keeps_its_commas(self) -> None:
        text = probe(extra='invariants: ["no evidence, requirement, or decision is invented", "shape only"]')
        manifest = prompts.parse_front_matter(text)
        self.assertEqual(len(manifest["invariants"]), 2)
        self.assertEqual(manifest["invariants"][0], "no evidence, requirement, or decision is invented")

    def test_an_unquoted_list_still_splits(self) -> None:
        manifest = prompts.parse_front_matter(probe(extra="fixtures: [one, two]"))
        self.assertEqual(manifest["fixtures"], ["one", "two"])

    def test_an_unbalanced_quote_is_reported(self) -> None:
        with self.assertRaises(prompts.MalformedFrontMatter):
            prompts.parse_front_matter(probe(extra='invariants: ["never closed]'))

    def test_quotes_are_delimiters_and_not_content(self) -> None:
        manifest = prompts.parse_front_matter(probe(extra='invariants: ["one"]'))
        self.assertEqual(manifest["invariants"], ["one"])


class DeclaredInvariantTests(unittest.TestCase):
    """#20: the manifest declares required invariants, and a request carries them."""

    def request(self) -> dict:
        path = ROOT / "evals" / "fixtures" / "reference.execution-request.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_both_prompts_declare_invariants(self) -> None:
        for path in sorted(prompts.PROMPTS.glob("*.md")):
            with self.subTest(prompt=path.name):
                manifest = prompts.parse_front_matter(path.read_text(encoding="utf-8"))
                self.assertTrue(manifest.get("invariants"), "a prompt promising nothing is not an interface")

    def test_each_invariant_reads_as_a_sentence_not_a_label(self) -> None:
        for path in sorted(prompts.PROMPTS.glob("*.md")):
            manifest = prompts.parse_front_matter(path.read_text(encoding="utf-8"))
            for invariant in manifest["invariants"]:
                with self.subTest(invariant=invariant):
                    self.assertGreater(len(invariant.split()), 3)

    def test_the_reference_request_carries_what_its_prompt_declares(self) -> None:
        self.assertEqual(prompts.request_invariant_violations(self.request()), [])

    def test_a_request_dropping_an_invariant_is_caught(self) -> None:
        request = self.request()
        request["invariants"] = request["invariants"][:-1]
        violations = prompts.request_invariant_violations(request)
        self.assertTrue(any("drops" in item for item in violations), violations)

    def test_a_request_inventing_an_invariant_is_caught(self) -> None:
        request = self.request()
        request["invariants"] = request["invariants"] + ["anything goes"]
        violations = prompts.request_invariant_violations(request)
        self.assertTrue(any("adds" in item for item in violations), violations)

    def test_order_does_not_matter(self) -> None:
        request = self.request()
        request["invariants"] = list(reversed(request["invariants"]))
        self.assertEqual(prompts.request_invariant_violations(request), [])

    def test_a_request_pinning_an_absent_prompt_is_caught(self) -> None:
        request = dict(self.request(), prompt_contract_id="frameshift.absent.v1")
        violations = prompts.request_invariant_violations(request)
        self.assertTrue(any("not installed" in item for item in violations), violations)

    def test_declaring_invariants_did_not_change_a_body_digest(self) -> None:
        """The manifest is front matter, and the digest covers only the body."""
        for path in sorted(prompts.PROMPTS.glob("*.md")):
            with self.subTest(prompt=path.name):
                text = path.read_text(encoding="utf-8")
                manifest = prompts.parse_front_matter(text)
                self.assertEqual(manifest["body_digest"], prompts.body_digest(text))

if __name__ == "__main__":
    unittest.main()
