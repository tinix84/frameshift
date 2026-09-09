#!/usr/bin/env python3
"""The MCP surface obtains disposition from client elicitation, not tool input."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.mcp.confirmation_server import ConfirmationMcpServer  # noqa: E402
from frameshift.orchestration.api import ConfirmationWorkflow  # noqa: E402


def load_session() -> dict:
    value = json.loads(
        (ROOT / "evals" / "fixtures" / "approval" / "gates.session.json").read_text(encoding="utf-8")
    )
    value["phase"] = "decision"
    return value


PROFILE = {
    "schema_version": "1.0.0",
    "id": "approval-profile-claude-code-2.1.265",
    "client_id": "claude-code",
    "client_version": "2.1.265",
    "config_digest": "sha256:" + "a" * 64,
    "validated": True,
}
ATTESTATION = {
    "schema_version": "1.0.0",
    "profile_id": PROFILE["id"],
    "client_id": PROFILE["client_id"],
    "client_version": PROFILE["client_version"],
    "config_digest": PROFILE["config_digest"],
    "operator": {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"},
    "attested_at": "2026-09-09T10:00:00Z",
}
TRANSITION = {
    "gate": "decision_approval",
    "target_id": "node_decision_001",
    "to_phase": "monitoring",
}


class ConfirmationMcpTests(unittest.TestCase):
    def server(self):
        workflow = ConfirmationWorkflow(load_session(), PROFILE)
        request = workflow.prepare(TRANSITION, ATTESTATION, request_id="confirm_mcp_001")
        server = ConfirmationMcpServer(
            workflow,
            lambda: dict(ATTESTATION),
            lambda: "2026-09-09T10:01:00Z",
        )
        server.initialize({"elicitation": {"form": {}}})
        return server, request

    def test_tool_arguments_carry_only_the_pending_request_id(self) -> None:
        server, _ = self.server()
        tool = server.list_tools()[0]
        self.assertEqual(tool["inputSchema"]["properties"], {"request_id": {"type": "string"}})
        self.assertEqual(tool["inputSchema"]["required"], ["request_id"])
        self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_native_elicitation_displays_every_bound_value_and_supplies_disposition(self) -> None:
        server, request = self.server()

        def elicit(parameters: dict) -> dict:
            message = parameters["message"]
            for value in (
                request["proposal"],
                request["request_digest"],
                str(request["session_revision"]),
                request["actor"]["id"],
            ):
                self.assertIn(value, message)
            enum = parameters["requestedSchema"]["properties"]["disposition"]["enum"]
            self.assertEqual(enum, request["permitted_dispositions"])
            return {"action": "accept", "content": {"disposition": "approved"}}

        result = server.call_tool("frameshift_confirm", {"request_id": request["id"]}, elicit)
        self.assertEqual(result["outcome"], "accepted", result)

    def test_a_model_cannot_put_an_actor_or_disposition_in_tool_arguments(self) -> None:
        server, request = self.server()
        called = []
        result = server.call_tool(
            "frameshift_confirm",
            {
                "request_id": request["id"],
                "disposition": "approved",
                "actor": {"kind": "human"},
            },
            called.append,
        )
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "schema_invalid")
        self.assertEqual(called, [])

    def test_a_client_without_form_elicitation_cannot_approve(self) -> None:
        server, request = self.server()
        server.initialize({})
        called = []
        result = server.call_tool("frameshift_confirm", {"request_id": request["id"]}, called.append)
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "unsupported_configuration")
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
