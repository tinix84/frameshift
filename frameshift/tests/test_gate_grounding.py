#!/usr/bin/env python3
"""The confirmation request shows the target's grounding profile (#277, ADR-0031).

When a gate targets a graph node, the person sees how much of it rests on
fact before deciding. The profile informs: it never refuses the gate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.broker.confirmation import request_digest  # noqa: E402
from frameshift.mcp.confirmation_server import elicitation_parameters  # noqa: E402
from frameshift.tests.test_sessions import Fixture, InCausal, approve  # noqa: E402
from frameshift.validation import validate_against  # noqa: E402


class AHypothesisGate(InCausal):
    def setUp(self) -> None:
        super().setUp()
        self.co.add_node(self.sid, node={"type": "hypothesis", "label": "Cell price dominates.", "source_ids": ["frame_001"]}, expected_revision=self.revision())

    def request(self) -> dict:
        return self.co.prepare_gate(self.sid, gate="evidence_sufficiency", target_id="node_001")

    def test_the_request_shows_the_targets_grounding_profile(self) -> None:
        request = self.request()
        profile = self.co.view(self.sid)["derived"]["grounding"]["nodes"]["node_001"]
        self.assertEqual(request["grounding"], profile)
        self.assertEqual(request["grounding"]["band"], "weak")
        self.assertEqual(request["grounding"]["bases"]["opinion"], ["node_001"])

    def test_the_request_stays_valid_and_its_digest_covers_the_profile(self) -> None:
        request = self.request()
        self.assertEqual(validate_against(request, "confirmation-request.schema.json"), [])
        self.assertEqual(request["request_digest"], request_digest(request))
        altered = dict(request, grounding=dict(request["grounding"], band="solid"))
        self.assertNotEqual(request_digest(altered), request["request_digest"])

    def test_a_weak_band_does_not_refuse_the_gate(self) -> None:
        approve(self.co, self.request())
        self.assertEqual(self.co.state(self.sid)["phase"], "solutions")

    def test_the_native_dialog_shows_the_band_and_the_weakest_base(self) -> None:
        message = elicitation_parameters(self.request())["message"]
        self.assertIn("Grounding band: weak", message)
        self.assertIn("Weakest base: node_001", message)


class AStatementOrFrameGate(Fixture):
    def test_a_gate_on_a_statement_or_a_frame_shows_no_grounding(self) -> None:
        self.classify()
        self.co.add_statement(self.sid, text="Pack cost per usable kWh meets the target.", primary_role="outcome", expected_revision=self.revision())
        request = self.co.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001")
        self.assertNotIn("grounding", request)
        self.assertNotIn("Grounding band", elicitation_parameters(request)["message"])


if __name__ == "__main__":
    unittest.main()
