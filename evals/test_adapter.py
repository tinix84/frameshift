#!/usr/bin/env python3
"""Tests that the round trip would fail if provider neutrality broke.

The fixtures prove two adapters agree on the reference checkpoint. These prove
the comparison is capable of disagreeing, that it tolerates exactly what
ADR-0001 says it may, and that a third adapter costs a manifest entry.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import adapter, canonical  # noqa: E402

AGREEMENT = "evals/fixtures/adapter-round-trip-yields-one-digest.case.json"
DIVERGENCE = "evals/fixtures/adapter-promotes-a-provider-request-id.case.json"


def reference_state() -> dict:
    return run.load("evals/fixtures/reference.checkpoint.json")["state"]


class ExtensionPointTests(unittest.TestCase):
    def test_extension_points_match_the_schemas(self) -> None:
        """The list is a mirror of where `extensions` is declared, not an opinion."""
        declared: set[str] = set()

        def walk(node: object, trail: tuple[str, ...] = ()) -> None:
            if isinstance(node, dict):
                for name, value in node.items():
                    if name == "extensions" and "properties" in trail[-1:]:
                        declared.add("extensions")
                    walk(value, trail + (name,))
            elif isinstance(node, list):
                for value in node:
                    walk(value, trail)

        for path in sorted((run.ROOT / "schemas").glob("*.json")):
            walk(json.loads(path.read_text(encoding="utf-8")))
        self.assertIn("extensions", declared)
        self.assertTrue(all(path[-1] == "extensions" for path in adapter.EXTENSION_POINTS))

    def test_extensions_are_stripped_only_where_the_schemas_allow_them(self) -> None:
        state = reference_state()
        state["extensions"] = {"x-a": 1}
        state["graph"]["nodes"][0]["extensions"] = {"x-a": 2}
        state["graph"]["edges"][0]["extensions"] = {"x-a": 3}
        state["statements"][0]["extensions"] = {"x-a": 4}
        stripped = adapter.neutral(state)
        self.assertNotIn("extensions", stripped)
        self.assertNotIn("extensions", stripped["graph"]["nodes"][0])
        self.assertNotIn("extensions", stripped["graph"]["edges"][0])
        # Not an extension point, so it stays and the adapters disagree over it.
        self.assertIn("extensions", stripped["statements"][0])


class RoundTripTests(unittest.TestCase):
    def test_the_agreement_case_passes(self) -> None:
        self.assertEqual(run.evaluate(run.load(AGREEMENT)), [])

    def test_the_divergence_case_passes(self) -> None:
        self.assertEqual(run.evaluate(run.load(DIVERGENCE)), [])

    def test_the_agreed_digest_is_the_checkpoints_own_state_digest(self) -> None:
        checkpoint = run.load("evals/fixtures/reference.checkpoint.json")
        for name in run.load(AGREEMENT)["adapters"]:
            round_tripped = adapter.neutral(adapter.ADAPTERS[name](copy.deepcopy(checkpoint["state"])))
            self.assertEqual(canonical.digest(round_tripped), checkpoint["state_digest"], name)

    def test_a_promoted_request_id_is_named_by_its_path(self) -> None:
        case = run.load(DIVERGENCE)
        case["expect"] = {"outcome": "agreed"}
        errors = run.evaluate(case)
        self.assertTrue(any("$.state.provider_request_id" in error for error in errors), errors)

    def test_a_divergence_deep_in_state_is_named_by_its_path(self) -> None:
        left = reference_state()
        right = copy.deepcopy(left)
        right["graph"]["nodes"][1]["label"] = "Something the other adapter never said."
        self.assertEqual(
            adapter.first_divergence(left, right), "$.state.graph.nodes[1].label"
        )

    def test_identical_states_do_not_diverge(self) -> None:
        left = reference_state()
        self.assertIsNone(adapter.first_divergence(left, copy.deepcopy(left)))

    def test_a_round_trip_needs_two_adapters(self) -> None:
        case = run.load(AGREEMENT)
        case["adapters"] = ["echo"]
        self.assertTrue(run.evaluate(case))

    def test_an_unknown_adapter_is_named(self) -> None:
        case = run.load(AGREEMENT)
        case["adapters"] = ["echo", "telepathy"]
        errors = run.evaluate(case)
        self.assertTrue(any("unknown adapter: telepathy" in error for error in errors), errors)


class ThirdAdapterTests(unittest.TestCase):
    """Adding an adapter costs a manifest entry and nothing else."""

    def setUp(self) -> None:
        self.manifest = dict(adapter.ADAPTERS)

    def tearDown(self) -> None:
        adapter.ADAPTERS.clear()
        adapter.ADAPTERS.update(self.manifest)

    def test_a_third_neutral_adapter_needs_no_new_runner(self) -> None:
        def whitespace_normalizing(state: dict) -> dict:
            """A provider that round-trips text through CRLF line endings."""
            if isinstance(state, dict):
                return {key: whitespace_normalizing(item) for key, item in state.items()}
            if isinstance(state, list):
                return [whitespace_normalizing(item) for item in state]
            if isinstance(state, str):
                return state.replace("\n", "\r\n")
            return state

        adapter.ADAPTERS["whitespace_normalizing"] = whitespace_normalizing
        case = run.load(AGREEMENT)
        case["adapters"] = case["adapters"] + ["whitespace_normalizing"]
        self.assertEqual(run.evaluate(case), [])

    def test_a_third_leaky_adapter_is_caught_by_the_same_runner(self) -> None:
        def token_counting(state: dict) -> dict:
            state["statements"][0]["token_counts"] = {"input": 2810, "output": 640}
            return state

        adapter.ADAPTERS["token_counting"] = token_counting
        case = run.load(AGREEMENT)
        case["adapters"] = ["echo", "token_counting"]
        errors = run.evaluate(case)
        self.assertTrue(
            any("$.state.statements[0].token_counts" in error for error in errors), errors
        )


class CorpusAcrossAdaptersTests(unittest.TestCase):
    """The corpus already written is the conformance suite an adapter faces."""

    CORPUS = "evals/fixtures/corpus-survives-every-adapter.case.json"

    def test_the_whole_corpus_survives_every_neutral_adapter(self) -> None:
        self.assertEqual(run.evaluate(run.load(self.CORPUS)), [])

    def test_a_leaky_adapter_breaks_the_corpus_and_is_named(self) -> None:
        case = run.load(self.CORPUS)
        case["transports"] = ["request_id_promoting"]
        errors = run.evaluate(case)
        self.assertTrue(errors, "a leaky adapter must not pass the corpus")
        self.assertTrue(all(item.startswith("request_id_promoting changed ") for item in errors), errors)

    def test_an_adapter_cannot_turn_a_refusal_into_a_transition(self) -> None:
        """#27's consequence clause: a gate is not something an adapter can cross."""
        case = run.load(self.CORPUS)
        case["corpus"] = ["approval_binding"]
        for name in ("echo", "reordering", "crlf_text"):
            with self.subTest(adapter=name):
                self.assertEqual(run.evaluate(dict(case, transports=[name])), [])

    def test_the_repair_corpus_runs_against_every_adapter(self) -> None:
        """#31's cross-adapter story: one standard for every adapter's output."""
        case = run.load(self.CORPUS)
        case["corpus"] = ["engine_result_repair"]
        self.assertEqual(run.evaluate(case), [])

    def test_an_unknown_transport_is_named(self) -> None:
        case = run.load(self.CORPUS)
        case["transports"] = ["telepathy"]
        errors = run.evaluate(case)
        self.assertTrue(any("unknown adapter: telepathy" in item for item in errors), errors)

    def test_a_corpus_naming_no_known_check_fails(self) -> None:
        case = run.load(self.CORPUS)
        case["corpus"] = ["nothing_declares_this"]
        self.assertTrue(run.evaluate(case))

    def test_a_case_without_transports_fails(self) -> None:
        case = run.load(self.CORPUS)
        case["transports"] = []
        self.assertTrue(run.evaluate(case))


if __name__ == "__main__":
    unittest.main()
