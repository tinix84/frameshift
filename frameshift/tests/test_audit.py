#!/usr/bin/env python3
"""Tests for the tool audit record (#23 FR-11).

FR-11 names four things to record. Having all four separately is not an audit
trail, so most of these are about whether the record is *faithful* — whether it
describes the call it claims to.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.broker import (  # noqa: E402
    authorize,
    record,
    record_violations,
    request_digest,
)
from frameshift.broker.audit import digest as record_digest  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures"
AT = "2026-07-15T09:14:00Z"
OWNER = {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"}


def request() -> dict:
    return json.loads((FIXTURES / "reference.tool-request.json").read_text(encoding="utf-8"))


def result() -> dict:
    return json.loads((FIXTURES / "reference.tool-result.json").read_text(encoding="utf-8"))


def manifest() -> dict:
    return json.loads((ROOT / "adapters" / "generic" / "capabilities.json").read_text(encoding="utf-8"))


def allowed_record() -> dict:
    req = request()
    return record(req, authorize(req, manifest()), AT, result())


class ContentTests(unittest.TestCase):
    """FR-11's four things, in one place."""

    def test_the_record_carries_the_request(self) -> None:
        entry = allowed_record()
        self.assertEqual(entry["request_id"], request()["request_id"])
        self.assertEqual(entry["request_digest"], request_digest(request()))

    def test_the_record_carries_the_result_digest(self) -> None:
        self.assertEqual(allowed_record()["result_digest"], result()["digest"])

    def test_the_record_carries_the_provenance(self) -> None:
        self.assertEqual(allowed_record()["provenance"], result()["provenance"])

    def test_the_record_carries_the_authorization(self) -> None:
        self.assertEqual(allowed_record()["authorization"]["outcome"], "allowed")

    def test_the_data_classes_are_repeated_so_the_record_stands_alone(self) -> None:
        """What left the session is the question an auditor asks first."""
        self.assertEqual(allowed_record()["data_classes"], request()["data_classes"])

    def test_the_committed_record_validates_and_is_faithful(self) -> None:
        entry = json.loads((FIXTURES / "reference.tool-audit-record.json").read_text(encoding="utf-8"))
        self.assertEqual(record_violations(entry, request(), result()), [])


class FaithfulnessTests(unittest.TestCase):
    def test_a_faithful_record_has_no_violations(self) -> None:
        self.assertEqual(record_violations(allowed_record(), request(), result()), [])

    def test_a_record_describing_a_different_request_is_caught(self) -> None:
        entry = allowed_record()
        entry["request_digest"] = "sha256:" + "0" * 64
        violations = record_violations(entry, request(), result())
        self.assertTrue(any("does not match the request" in item for item in violations), violations)

    def test_a_record_describing_a_different_result_is_caught(self) -> None:
        entry = allowed_record()
        entry["result_digest"] = "sha256:" + "1" * 64
        violations = record_violations(entry, request(), result())
        self.assertTrue(any("does not match the result" in item for item in violations), violations)

    def test_a_refused_call_carrying_a_result_is_caught(self) -> None:
        """The single most important thing an audit of tool use can catch."""
        entry = record(request(), ["tool_policy_denied: no"], AT, result())
        violations = record_violations(entry, request(), result())
        self.assertTrue(any("something executed" in item for item in violations), violations)

    def test_a_refused_call_with_no_result_is_faithful(self) -> None:
        entry = record(request(), ["tool_policy_denied: no"], AT, None)
        self.assertEqual(record_violations(entry, request(), None), [])
        self.assertEqual(entry["authorization"]["outcome"], "refused")

    def test_a_signature_bound_to_something_else_is_caught(self) -> None:
        req = dict(request(), approval="each_call")
        approval = {
            "target_digest": "sha256:" + "2" * 64,
            "actor": OWNER,
            "disposition": "approved",
        }
        entry = record(req, [], AT, result(), approval)
        violations = record_violations(entry, req, result())
        self.assertTrue(any("not to the request it authorized" in item for item in violations), violations)

    def test_a_correctly_bound_signature_is_recorded(self) -> None:
        req = dict(request(), approval="each_call")
        approval = {
            "target_digest": request_digest(req),
            "actor": OWNER,
            "disposition": "approved",
        }
        entry = record(req, [], AT, result(), approval)
        self.assertEqual(record_violations(entry, req, result()), [])
        self.assertEqual(entry["authorization"]["approved_by"], OWNER)


class TamperTests(unittest.TestCase):
    def test_the_record_digests_so_a_trail_can_be_checked(self) -> None:
        entry = allowed_record()
        before = record_digest(entry)
        self.assertEqual(record_digest(dict(entry)), before)
        entry["operation"] = "something-else"
        self.assertNotEqual(record_digest(entry), before)

    def test_the_digest_is_canonical(self) -> None:
        entry = allowed_record()
        reordered = {key: entry[key] for key in reversed(list(entry))}
        self.assertEqual(record_digest(entry), record_digest(reordered))


if __name__ == "__main__":
    unittest.main()
