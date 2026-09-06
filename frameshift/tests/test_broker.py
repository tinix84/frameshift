#!/usr/bin/env python3
"""Tests for the capability broker port (#21, #24).

Four of #21's seven lifecycle steps are checkable without a runtime, and each
of these breaks exactly one of them. The binding test is the one that matters
most: without it a signature given for one call can be spent on another.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.broker import (  # noqa: E402
    APPROVAL_REQUIRED,
    APPROVAL_STALE,
    CAPABILITY_UNAVAILABLE,
    DATA_CLASS_NOT_ALLOWED,
    TOOL_POLICY_DENIED,
    accept_result,
    authorize,
    needs_approval,
    request_digest,
    execute,
    RETRY_CONFIRMATION_REQUIRED,
)

FIXTURES = ROOT / "evals" / "fixtures"
OWNER = {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"}


def request() -> dict:
    return json.loads((FIXTURES / "reference.tool-request.json").read_text(encoding="utf-8"))


def result() -> dict:
    return json.loads((FIXTURES / "reference.tool-result.json").read_text(encoding="utf-8"))


def manifest(name: str = "generic") -> dict:
    return json.loads((ROOT / "adapters" / name / "capabilities.json").read_text(encoding="utf-8"))


def approval_for(req: dict, **overrides) -> dict:
    base = {
        "id": "appr_tool_001",
        "target_id": req["request_id"],
        "target_digest": request_digest(req),
        "disposition": "approved",
        "actor": OWNER,
        "created_at": "2026-07-15T09:13:57Z",
    }
    base.update(overrides)
    return base


class CleanPathTests(unittest.TestCase):
    def test_the_committed_request_is_authorized(self) -> None:
        self.assertEqual(authorize(request(), manifest()), [])

    def test_the_committed_result_is_accepted(self) -> None:
        self.assertEqual(accept_result(request(), result()), [])

    def test_a_request_needing_no_approval_needs_none(self) -> None:
        self.assertFalse(needs_approval(request()))


class ResolutionTests(unittest.TestCase):
    def test_a_capability_the_profile_does_not_offer_is_refused(self) -> None:
        refusals = authorize(dict(request(), capability_id="web.retrieve"), manifest())
        self.assertTrue(any(item.startswith(CAPABILITY_UNAVAILABLE) for item in refusals), refusals)

    def test_a_capability_declared_unavailable_is_refused(self) -> None:
        """claude-code declares external.connector with available: false."""
        asking = dict(
            request(),
            capability_id="external.connector",
            operation="invoke",
            side_effect="external",
            approval="policy",
        )
        refusals = authorize(asking, manifest("claude-code"))
        self.assertTrue(any(item.startswith(CAPABILITY_UNAVAILABLE) for item in refusals), refusals)

    def test_an_operation_the_capability_does_not_declare_is_refused(self) -> None:
        refusals = authorize(dict(request(), operation="delete-everything"), manifest())
        self.assertTrue(any(item.startswith(TOOL_POLICY_DENIED) for item in refusals), refusals)


class PolicyCeilingTests(unittest.TestCase):
    """The manifest is a ceiling, not a suggestion."""

    def test_a_request_cannot_ask_for_a_looser_gate(self) -> None:
        strict = copy.deepcopy(manifest("claude-code"))
        target = next(c for c in strict["capabilities"] if c["id"] == "artifact.write")
        target["approval"] = "each_call"
        asking = dict(
            request(), capability_id="artifact.write", operation="write-file",
            side_effect="reversible", approval="never",
        )
        refusals = authorize(asking, strict)
        self.assertTrue(any("asks for approval" in item for item in refusals), refusals)

    def test_a_request_cannot_claim_a_milder_side_effect(self) -> None:
        asking = dict(
            request(), capability_id="artifact.write", operation="write-file",
            side_effect="none", approval="policy",
        )
        refusals = authorize(asking, manifest("claude-code"))
        self.assertTrue(any("claims side effect" in item for item in refusals), refusals)

    def test_a_stricter_request_is_allowed(self) -> None:
        """Asking for more scrutiny than required is never the problem."""
        asking = dict(request(), approval="each_call", side_effect="reversible")
        refusals = authorize(asking, manifest(), approval_for(asking))
        self.assertEqual(refusals, [])

    def test_a_data_class_the_capability_does_not_accept_is_refused(self) -> None:
        asking = dict(request(), data_classes=["user-provided", "credentials"])
        refusals = authorize(asking, manifest())
        self.assertTrue(any(item.startswith(DATA_CLASS_NOT_ALLOWED) for item in refusals), refusals)
        self.assertTrue(any("credentials" in item for item in refusals))


class ApprovalBindingTests(unittest.TestCase):
    """#21 step 4, and the reason it exists."""

    def each_call(self) -> dict:
        return dict(request(), approval="each_call")

    def test_a_call_needing_approval_without_one_is_refused(self) -> None:
        refusals = authorize(self.each_call(), manifest(), None)
        self.assertTrue(any(item.startswith(APPROVAL_REQUIRED) for item in refusals), refusals)

    def test_a_correctly_bound_approval_authorizes(self) -> None:
        asking = self.each_call()
        self.assertEqual(authorize(asking, manifest(), approval_for(asking)), [])

    def test_an_approval_for_a_different_call_cannot_be_spent_here(self) -> None:
        """A signature given for 'read this' must not authorize 'send that'."""
        signed = self.each_call()
        other = dict(signed, arguments={"artifact_id": "art_something_else"})
        refusals = authorize(other, manifest(), approval_for(signed))
        self.assertTrue(any(item.startswith(APPROVAL_STALE) for item in refusals), refusals)

    def test_changing_any_declared_field_breaks_the_binding(self) -> None:
        signed = self.each_call()
        approval = approval_for(signed)
        for field, value in (
            ("purpose", "Something else entirely."),
            ("data_classes", ["user-provided", "workspace"]),
            ("side_effect", "reversible"),
            ("operation", "read-inline "),
        ):
            with self.subTest(field=field):
                altered = dict(signed, **{field: value})
                if authorize(altered, manifest(), approval) == []:
                    self.fail(f"changing {field} did not break the binding")

    def test_a_rejected_disposition_does_not_authorize(self) -> None:
        asking = self.each_call()
        refusals = authorize(asking, manifest(), approval_for(asking, disposition="rejected"))
        self.assertTrue(any(item.startswith(APPROVAL_REQUIRED) for item in refusals), refusals)

    def test_a_runtime_cannot_approve_a_tool_call(self) -> None:
        asking = self.each_call()
        robot = {"id": "bot", "kind": "runtime", "role": "decision_owner"}
        refusals = authorize(asking, manifest(), approval_for(asking, actor=robot))
        self.assertTrue(any("cannot approve" in item for item in refusals), refusals)

    def test_the_digest_is_canonical(self) -> None:
        """Reordering the request's keys must not change what was signed."""
        original = self.each_call()
        reordered = {key: original[key] for key in reversed(list(original))}
        self.assertEqual(request_digest(original), request_digest(reordered))


class ResultTests(unittest.TestCase):
    def test_a_result_answering_another_request_is_refused(self) -> None:
        refusals = accept_result(request(), dict(result(), request_id="tool_other_001"))
        self.assertTrue(any(item.startswith(TOOL_POLICY_DENIED) for item in refusals), refusals)

    def test_a_success_with_nothing_returned_is_refused(self) -> None:
        empty = {key: value for key, value in result().items() if key != "artifact"}
        refusals = accept_result(request(), empty)
        self.assertTrue(any("neither output nor an artifact" in item for item in refusals), refusals)

    def test_a_result_carries_provenance_and_a_digest(self) -> None:
        for field in ("provenance", "digest"):
            with self.subTest(field=field):
                stripped = {k: v for k, v in result().items() if k != field}
                self.assertTrue(accept_result(request(), stripped))

    def test_there_is_nowhere_to_put_an_approval_or_a_proposal(self) -> None:
        """Tool output is untrusted input: the shape itself denies it authority."""
        for smuggled in ("approvals", "proposals", "instructions"):
            with self.subTest(field=smuggled):
                refusals = accept_result(request(), dict(result(), **{smuggled: []}))
                self.assertTrue(refusals, f"{smuggled} was accepted into a tool result")

    def test_a_denied_call_needs_no_output(self) -> None:
        denied = {k: v for k, v in result().items() if k != "artifact"}
        denied["status"] = "denied"
        denied["denied_reason"] = "Workspace policy forbids external reads."
        self.assertEqual(accept_result(request(), denied), [])


class ExecutionTests(unittest.TestCase):
    def test_unavailable_capability_returns_a_structured_gap_and_never_executes(self) -> None:
        calls = []
        outcome = execute(dict(request(), capability_id="missing.lookup"), manifest(), calls.append, recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(outcome["status"], "denied")
        self.assertTrue(outcome["alternatives"])
        self.assertEqual(calls, [])

    def test_policy_denial_happens_before_the_injected_executor(self) -> None:
        calls = []
        outcome = execute(dict(request(), operation="delete-everything"), manifest(), calls.append, recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(outcome["status"], "denied")
        self.assertEqual(calls, [])
        self.assertEqual(outcome["audit"]["authorization"]["outcome"], "refused")

    def test_retry_without_idempotency_support_requires_confirmation(self) -> None:
        calls = []
        req = request()
        profile = copy.deepcopy(manifest())
        profile["capabilities"][0]["idempotent"] = False
        first = execute(req, profile, lambda value: (calls.append(value) or result()), recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(first["status"], "succeeded")
        second = execute(req, profile, lambda value: (calls.append(value) or result()), prior_requests={req["idempotency_key"]: request_digest(req)}, recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(second["status"], "denied")
        self.assertTrue(second["denied_reason"].startswith(RETRY_CONFIRMATION_REQUIRED))
        self.assertEqual(len(calls), 1)

    def test_failed_execution_is_still_a_retry_requiring_confirmation(self) -> None:
        req = request()
        prior = {}
        first = execute(req, manifest(), lambda _: {}, prior_requests=prior, recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(first["status"], "failed")
        second = execute(req, manifest(), lambda _: result(), prior_requests=prior, recorded_at="2026-07-15T09:14:00Z")
        self.assertTrue(second["denied_reason"].startswith(RETRY_CONFIRMATION_REQUIRED))

    def test_executor_exception_still_records_an_attempt_for_retry(self) -> None:
        req = request()
        prior = {}
        def executor(_):
            raise RuntimeError("synthetic execution failure")
        first = execute(req, manifest(), executor, prior_requests=prior, recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first["audit"]["authorization"]["outcome"], "allowed")
        self.assertIsNone(first["audit"]["result_digest"])
        self.assertEqual(first["audit"]["execution_error"], "execution_failed: RuntimeError")
        second = execute(req, manifest(), lambda _: result(), prior_requests=prior, recorded_at="2026-07-15T09:14:00Z")
        self.assertTrue(second["denied_reason"].startswith(RETRY_CONFIRMATION_REQUIRED))

    def test_retry_requires_a_human_bound_to_this_request(self) -> None:
        req = request()
        for approval in (
            approval_for(req, actor={"id": "bot", "kind": "runtime"}),
            approval_for(dict(req, purpose="A different request")),
        ):
            outcome = execute(req, manifest(), lambda _: result(), retry_approval=approval,
                              prior_requests={req["idempotency_key"]: request_digest(req)},
                              recorded_at="2026-07-15T09:14:00Z")
            self.assertTrue(outcome["denied_reason"].startswith(RETRY_CONFIRMATION_REQUIRED))
        approval = approval_for(req)
        outcome = execute(req, manifest(), lambda _: result(), retry_approval=approval,
                          prior_requests={req["idempotency_key"]: request_digest(req)},
                          recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(outcome["audit"]["authorization"]["approved_by"], approval["actor"])

    def test_executed_audit_records_destination_and_result_digest(self) -> None:
        req = request()
        outcome = execute(req, manifest(), lambda _: result(), recorded_at="2026-07-15T09:14:00Z")
        self.assertEqual(outcome["audit"]["capability_id"], req["capability_id"])
        self.assertEqual(outcome["audit"]["operation"], req["operation"])
        self.assertEqual(outcome["audit"]["data_classes"], req["data_classes"])
        self.assertEqual(outcome["audit"]["destination"], req["destination"])
        self.assertEqual(outcome["audit"]["result_digest"], result()["digest"])


if __name__ == "__main__":
    unittest.main()
