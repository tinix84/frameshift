#!/usr/bin/env python3
"""Tests for the runtime adapter port.

The port enforces the three things checkable from outside a runtime: the
request is valid, the result and envelope are valid and agree with each other,
and the answer is about the execution that was asked. Each test breaks exactly
one of them.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.adapters import (  # noqa: E402
    Adapter,
    EchoAdapter,
    ExecutionOutcome,
    run,
    unsupported,
)

FIXTURES = ROOT / "evals" / "fixtures"


def request() -> dict:
    return json.loads((FIXTURES / "reference.execution-request.json").read_text(encoding="utf-8"))


def result() -> dict:
    return json.loads(
        (FIXTURES / "framing-solution-disguised.result.json").read_text(encoding="utf-8")
    )


def manifest() -> dict:
    return json.loads((ROOT / "adapters" / "generic" / "capabilities.json").read_text(encoding="utf-8"))


class Broken(EchoAdapter):
    """An adapter that answers wrongly in exactly one way."""

    def __init__(self, result: dict, **damage) -> None:
        super().__init__(result)
        self.damage = damage

    def execute(self, request: dict) -> ExecutionOutcome:
        outcome = super().execute(request)
        for key, value in self.damage.items():
            if key.startswith("envelope_"):
                outcome.envelope[key[len("envelope_"):]] = value
            else:
                outcome.result[key] = value
        return outcome


class PortShapeTests(unittest.TestCase):
    def test_the_echo_adapter_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(EchoAdapter(result()), Adapter)

    def test_it_reports_a_capability_manifest(self) -> None:
        adapter = EchoAdapter(result(), manifest())
        self.assertEqual(adapter.capabilities()["profile_id"], "generic-conversation-only")


class HappyPathTests(unittest.TestCase):
    def test_a_valid_request_yields_an_accepted_outcome(self) -> None:
        outcome = run(EchoAdapter(result()), request())
        self.assertTrue(outcome.accepted, outcome.violations)

    def test_the_answer_is_normalized_onto_the_request(self) -> None:
        asked = request()
        outcome = run(EchoAdapter(result()), asked)
        self.assertEqual(outcome.result["execution_id"], asked["execution_id"])
        self.assertEqual(outcome.envelope["execution_id"], asked["execution_id"])
        self.assertEqual(outcome.result["input_revision"], asked["session_revision"])

    def test_the_committed_reference_request_is_valid(self) -> None:
        from frameshift.validation import validate_against

        self.assertEqual(validate_against(request(), "execution-request.schema.json"), [])


class RefusalTests(unittest.TestCase):
    def test_an_invalid_request_is_refused_without_running_the_adapter(self) -> None:
        class Exploding(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                raise AssertionError("the adapter must not be called")

        broken = request()
        del broken["input_state_digest"]
        outcome = run(Exploding(result()), broken)
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("request" in item for item in outcome.violations))

    def test_an_invalid_result_is_caught(self) -> None:
        outcome = run(Broken(result(), status="finished"), request())
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("runtime_output_invalid" in item for item in outcome.violations))

    def test_an_envelope_claiming_valid_over_an_invalid_result_is_caught(self) -> None:
        """The one lie the port can catch on its own, and the one worth catching."""
        outcome = run(Broken(result(), status="finished"), request())
        self.assertTrue(
            any("envelope reports 'valid'" in item for item in outcome.violations),
            outcome.violations,
        )

    def test_answering_a_different_execution_is_caught(self) -> None:
        outcome = run(Broken(result(), execution_id="exec_somebody_else"), request())
        self.assertTrue(any("answers execution" in item for item in outcome.violations))

    def test_an_envelope_answering_a_different_execution_is_caught(self) -> None:
        outcome = run(Broken(result(), envelope_execution_id="exec_somebody_else"), request())
        self.assertTrue(any("envelope answers execution" in item for item in outcome.violations))

    def test_a_result_from_another_engine_is_caught(self) -> None:
        outcome = run(Broken(result(), engine="causal_reasoning"), request())
        self.assertTrue(any("is from engine" in item for item in outcome.violations))

    def test_a_result_against_another_revision_is_caught(self) -> None:
        outcome = run(Broken(result(), input_revision=99), request())
        self.assertTrue(any("against revision" in item for item in outcome.violations))

    def test_an_invalid_envelope_is_caught(self) -> None:
        outcome = run(Broken(result(), envelope_stop_reason="vibes"), request())
        self.assertTrue(any("envelope" in item for item in outcome.violations))

    def test_an_adapters_own_violations_survive(self) -> None:
        class Honest(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                outcome = super().execute(request)
                outcome.violations.append("capability_unavailable: web.retrieve")
                return outcome

        outcome = run(Honest(result()), request())
        self.assertIn("capability_unavailable: web.retrieve", outcome.violations)


class NoNewFactsTests(unittest.TestCase):
    def test_normalizing_changes_only_what_the_request_pins(self) -> None:
        """An adapter normalizes; it does not add domain content."""
        before = result()
        outcome = run(EchoAdapter(copy.deepcopy(before)), request())
        expected = copy.deepcopy(before)
        asked = request()
        expected["execution_id"] = asked["execution_id"]
        expected["engine"] = asked["engine"]
        expected["input_revision"] = asked["session_revision"]
        self.assertEqual(outcome.result, expected)

    def test_the_proposals_are_carried_through_untouched(self) -> None:
        before = result()
        outcome = run(EchoAdapter(copy.deepcopy(before)), request())
        self.assertEqual(outcome.result["proposals"], before["proposals"])
        self.assertEqual(outcome.result["rationale_summaries"], before["rationale_summaries"])


class UnsupportedCapabilityTests(unittest.TestCase):
    """#19 responsibility 9: return unsupported capabilities explicitly."""

    def claude_code(self) -> dict:
        return json.loads(
            (ROOT / "adapters" / "claude-code" / "capabilities.json").read_text(encoding="utf-8")
        )

    def asking(self, *names: str) -> dict:
        return dict(result(), requested_capabilities=list(names))

    def test_a_capability_absent_from_the_manifest_is_unsupported(self) -> None:
        self.assertEqual(
            unsupported(["web.retrieve", "artifact.read"], manifest()), ["web.retrieve"]
        )

    def test_a_capability_declared_but_unavailable_is_unsupported(self) -> None:
        """claude-code declares external.connector with available: false."""
        self.assertEqual(unsupported(["external.connector"], self.claude_code()), ["external.connector"])

    def test_an_offered_capability_is_supported(self) -> None:
        self.assertEqual(unsupported(["artifact.read"], self.claude_code()), [])

    def test_an_empty_manifest_supports_nothing(self) -> None:
        self.assertEqual(unsupported(["artifact.read"], {}), ["artifact.read"])

    def test_an_honest_adapter_reports_and_is_accepted(self) -> None:
        outcome = run(EchoAdapter(self.asking("external.connector"), self.claude_code()), request())
        self.assertTrue(outcome.accepted, outcome.violations)
        self.assertEqual(outcome.envelope["unsupported_capabilities"], ["external.connector"])

    def test_a_silent_adapter_is_caught(self) -> None:
        """Silence reads as 'it was done', which is the failure worth catching."""

        class Silent(EchoAdapter):
            def execute(self, request):
                outcome = super().execute(request)
                outcome.envelope["unsupported_capabilities"] = []
                return outcome

        outcome = run(Silent(self.asking("external.connector"), self.claude_code()), request())
        self.assertFalse(outcome.accepted)
        self.assertTrue(
            any(item.startswith("capability_unavailable") for item in outcome.violations),
            outcome.violations,
        )

    def test_reporting_more_than_required_is_allowed(self) -> None:
        """Only the adapter knows a connector is down today."""

        class Cautious(EchoAdapter):
            def execute(self, request):
                outcome = super().execute(request)
                outcome.envelope["unsupported_capabilities"] = ["artifact.read", "external.connector"]
                return outcome

        outcome = run(Cautious(self.asking("external.connector"), self.claude_code()), request())
        self.assertTrue(outcome.accepted, outcome.violations)

    def test_requesting_nothing_needs_no_report(self) -> None:
        outcome = run(EchoAdapter(self.asking(), self.claude_code()), request())
        self.assertTrue(outcome.accepted, outcome.violations)

    def test_the_committed_manifests_all_parse_into_the_check(self) -> None:
        for name in ("generic", "claude-code", "codex"):
            with self.subTest(adapter=name):
                loaded = json.loads(
                    (ROOT / "adapters" / name / "capabilities.json").read_text(encoding="utf-8")
                )
                self.assertEqual(unsupported(["artifact.read"], loaded), [])


if __name__ == "__main__":
    unittest.main()
