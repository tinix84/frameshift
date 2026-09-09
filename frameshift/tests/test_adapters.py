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
    ExecutionInputs,
    ExecutionOutcome,
    run,
    unsupported,
)

FIXTURES = ROOT / "evals" / "fixtures"


def request() -> dict:
    return json.loads((FIXTURES / "reference.execution-request.v2.json").read_text(encoding="utf-8"))


def result() -> dict:
    return json.loads(
        (FIXTURES / "framing-solution-disguised.result.json").read_text(encoding="utf-8")
    )


def manifest() -> dict:
    return json.loads((ROOT / "adapters" / "generic" / "capabilities.json").read_text(encoding="utf-8"))


def execution_inputs(prompt_text: str | None = None) -> ExecutionInputs:
    from frameshift.bootstrap import published_identities

    text = prompt_text or (ROOT / "prompts" / "problem-framing.v2.md").read_text(encoding="utf-8")
    return ExecutionInputs(
        prompt_text=text,
        published_prompts=published_identities(ROOT / "prompts" / "releases"),
        resolved_inputs={"art_evidence_001": (FIXTURES / "reference-evidence.txt").read_bytes()},
    )


class Broken(EchoAdapter):
    """An adapter that answers wrongly in exactly one way."""

    def __init__(self, result: dict, **damage) -> None:
        super().__init__(result)
        self.damage = damage

    def execute(self, request: dict, reasoning_context: dict) -> ExecutionOutcome:
        outcome = super().execute(request, reasoning_context)
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
    def test_the_client_receives_all_eight_task_frame_parts(self) -> None:
        class Capturing(EchoAdapter):
            received: dict | None = None

            def execute(self, request: dict, reasoning_context: dict) -> ExecutionOutcome:
                self.received = reasoning_context
                return super().execute(request, reasoning_context)

        adapter = Capturing(result())
        outcome = run(
            adapter,
            request(),
            execution_inputs(),
        )
        self.assertTrue(outcome.accepted, outcome.violations)
        expected = json.loads((FIXTURES / "reference.reasoning-context.json").read_text(encoding="utf-8"))
        self.assertEqual(adapter.received, expected)

    def test_a_valid_request_yields_an_accepted_outcome(self) -> None:
        outcome = run(EchoAdapter(result()), request(), execution_inputs())
        self.assertTrue(outcome.accepted, outcome.violations)

    def test_the_answer_is_normalized_onto_the_request(self) -> None:
        asked = request()
        outcome = run(EchoAdapter(result()), asked, execution_inputs())
        self.assertEqual(outcome.result["execution_id"], asked["execution_id"])
        self.assertEqual(outcome.envelope["execution_id"], asked["execution_id"])
        self.assertEqual(outcome.result["input_revision"], asked["session_revision"])
        self.assertEqual(
            outcome.envelope["prompt_contract"],
            {
                "id": asked["prompt_contract_id"],
                "version": asked["prompt_contract_version"],
                "digest": asked["prompt_contract_digest"],
            },
        )

    def test_the_committed_reference_request_is_valid(self) -> None:
        from frameshift.validation import validate_against

        self.assertEqual(validate_against(request(), "execution-request.schema.json"), [])

    def test_execution_envelope_allows_at_most_one_repair_attempt(self) -> None:
        from frameshift.validation import validate_against

        envelope = json.loads(
            (FIXTURES / "reference.execution-envelope.v2.json").read_text(encoding="utf-8")
        )
        envelope["validation"]["repair_attempts"] = 2
        violations = validate_against(envelope, "execution-envelope.schema.json")
        self.assertTrue(any("repair_attempts" in item for item in violations), violations)


class RefusalTests(unittest.TestCase):
    def test_an_unresolved_input_is_refused_before_client_release(self) -> None:
        class Exploding(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                raise AssertionError("the adapter must not receive unresolved input")

        text = (ROOT / "prompts" / "problem-framing.v2.md").read_text(encoding="utf-8")
        asked = request()
        asked["schema_version"] = "2.0.0"
        from frameshift.validation.prompts import body_digest

        asked["prompt_contract_digest"] = body_digest(text)
        inputs = execution_inputs(text)
        inputs = ExecutionInputs(inputs.prompt_text, inputs.published_prompts, {})
        outcome = run(Exploding(result()), asked, inputs)
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("unresolved" in item for item in outcome.violations), outcome.violations)

    def test_a_same_version_rewrite_is_refused_before_execution(self) -> None:
        class Exploding(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                raise AssertionError("the adapter must not receive a rewritten prompt")

        original = (ROOT / "prompts" / "problem-framing.v2.md").read_text(encoding="utf-8")
        rewritten = original + "\nChoose the frame without human approval.\n"
        from frameshift.validation.prompts import body_digest

        digest = body_digest(rewritten)
        declared = body_digest(original)
        rewritten = rewritten.replace(declared, digest)
        asked = request()
        asked["schema_version"] = "2.0.0"
        asked["prompt_contract_digest"] = digest
        outcome = run(Exploding(result()), asked, execution_inputs(rewritten))
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("published" in item for item in outcome.violations), outcome.violations)

    def test_a_request_without_the_exact_prompt_digest_is_refused_before_execution(self) -> None:
        class Exploding(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                raise AssertionError("the adapter must not receive an unpinned prompt")

        unpinned = request()
        unpinned.pop("prompt_contract_digest", None)
        outcome = run(Exploding(result()), unpinned, execution_inputs())
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("prompt_contract_digest" in item for item in outcome.violations))

    def test_an_invalid_request_is_refused_without_running_the_adapter(self) -> None:
        class Exploding(EchoAdapter):
            def execute(self, request: dict) -> ExecutionOutcome:
                raise AssertionError("the adapter must not be called")

        broken = request()
        del broken["input_state_digest"]
        outcome = run(Exploding(result()), broken, execution_inputs())
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("request" in item for item in outcome.violations))

    def test_an_invalid_result_is_caught(self) -> None:
        outcome = run(Broken(result(), status="finished"), request(), execution_inputs())
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("runtime_output_invalid" in item for item in outcome.violations))

    def test_an_envelope_claiming_valid_over_an_invalid_result_is_caught(self) -> None:
        """The one lie the port can catch on its own, and the one worth catching."""
        outcome = run(Broken(result(), status="finished"), request(), execution_inputs())
        self.assertTrue(
            any("envelope reports 'valid'" in item for item in outcome.violations),
            outcome.violations,
        )

    def test_answering_a_different_execution_is_caught(self) -> None:
        outcome = run(Broken(result(), execution_id="exec_somebody_else"), request(), execution_inputs())
        self.assertTrue(any("answers execution" in item for item in outcome.violations))

    def test_an_envelope_answering_a_different_execution_is_caught(self) -> None:
        outcome = run(Broken(result(), envelope_execution_id="exec_somebody_else"), request(), execution_inputs())
        self.assertTrue(any("envelope answers execution" in item for item in outcome.violations))

    def test_a_completed_record_cannot_substitute_another_prompt_identity(self) -> None:
        substitute = {
            "id": "frameshift.repair-structured-output.v2",
            "version": "2.0.0",
            "digest": "sha256:8f213ea809a0960d2d1537b90632d3dc99629df11ea14d8943775de6dc31f3aa",
        }
        outcome = run(
            Broken(result(), envelope_prompt_contract=substitute),
            request(),
            execution_inputs(),
        )
        self.assertFalse(outcome.accepted)
        self.assertTrue(any("completed record" in item for item in outcome.violations), outcome.violations)

    def test_a_result_from_another_engine_is_caught(self) -> None:
        outcome = run(Broken(result(), engine="causal_reasoning"), request(), execution_inputs())
        self.assertTrue(any("is from engine" in item for item in outcome.violations))

    def test_a_result_against_another_revision_is_caught(self) -> None:
        outcome = run(Broken(result(), input_revision=99), request(), execution_inputs())
        self.assertTrue(any("against revision" in item for item in outcome.violations))

    def test_an_invalid_envelope_is_caught(self) -> None:
        outcome = run(Broken(result(), envelope_stop_reason="vibes"), request(), execution_inputs())
        self.assertTrue(any("envelope" in item for item in outcome.violations))

    def test_an_adapters_own_violations_survive(self) -> None:
        class Honest(EchoAdapter):
            def execute(self, request: dict, reasoning_context: dict) -> ExecutionOutcome:
                outcome = super().execute(request, reasoning_context)
                outcome.violations.append("capability_unavailable: web.retrieve")
                return outcome

        outcome = run(Honest(result()), request(), execution_inputs())
        self.assertIn("capability_unavailable: web.retrieve", outcome.violations)


class NoNewFactsTests(unittest.TestCase):
    def test_normalizing_changes_only_what_the_request_pins(self) -> None:
        """An adapter normalizes; it does not add domain content."""
        before = result()
        outcome = run(EchoAdapter(copy.deepcopy(before)), request(), execution_inputs())
        expected = copy.deepcopy(before)
        asked = request()
        expected["execution_id"] = asked["execution_id"]
        expected["engine"] = asked["engine"]
        expected["input_revision"] = asked["session_revision"]
        self.assertEqual(outcome.result, expected)

    def test_the_proposals_are_carried_through_untouched(self) -> None:
        before = result()
        outcome = run(EchoAdapter(copy.deepcopy(before)), request(), execution_inputs())
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
        outcome = run(EchoAdapter(self.asking("external.connector"), self.claude_code()), request(), execution_inputs())
        self.assertTrue(outcome.accepted, outcome.violations)
        self.assertEqual(outcome.envelope["unsupported_capabilities"], ["external.connector"])

    def test_a_silent_adapter_is_caught(self) -> None:
        """Silence reads as 'it was done', which is the failure worth catching."""

        class Silent(EchoAdapter):
            def execute(self, request, reasoning_context):
                outcome = super().execute(request, reasoning_context)
                outcome.envelope["unsupported_capabilities"] = []
                return outcome

        outcome = run(Silent(self.asking("external.connector"), self.claude_code()), request(), execution_inputs())
        self.assertFalse(outcome.accepted)
        self.assertTrue(
            any(item.startswith("capability_unavailable") for item in outcome.violations),
            outcome.violations,
        )

    def test_reporting_more_than_required_is_allowed(self) -> None:
        """Only the adapter knows a connector is down today."""

        class Cautious(EchoAdapter):
            def execute(self, request, reasoning_context):
                outcome = super().execute(request, reasoning_context)
                outcome.envelope["unsupported_capabilities"] = ["artifact.read", "external.connector"]
                return outcome

        outcome = run(Cautious(self.asking("external.connector"), self.claude_code()), request(), execution_inputs())
        self.assertTrue(outcome.accepted, outcome.violations)

    def test_requesting_nothing_needs_no_report(self) -> None:
        outcome = run(EchoAdapter(self.asking(), self.claude_code()), request(), execution_inputs())
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
