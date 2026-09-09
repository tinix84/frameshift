#!/usr/bin/env python3
"""The MCP surface obtains disposition from client elicitation, not tool input."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.mcp.confirmation_server import ConfirmationMcpServer, run_stdio  # noqa: E402
from frameshift.orchestration.api import ConfirmationWorkflow  # noqa: E402
from frameshift.broker.confirmation import approval_configuration_refusal  # noqa: E402


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
            lambda: dict(PROFILE),
            lambda: "2026-09-09T10:01:00Z",
        )
        server.initialize(
            {"elicitation": {"form": {}}},
            {"name": "claude-code", "version": "2.1.265"},
        )
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
        self.assertEqual(result["outcome"], "confirmed", result)

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
        server.initialize({}, {"name": "claude-code", "version": "2.1.265"})
        called = []
        result = server.call_tool("frameshift_confirm", {"request_id": request["id"]}, called.append)
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["code"], "unsupported_configuration")
        self.assertEqual(called, [])

    def test_an_edit_is_followed_by_a_second_native_dialog_without_model_help(self) -> None:
        server, request = self.server()
        calls = []

        def elicit(parameters: dict) -> dict:
            calls.append(parameters)
            if len(calls) == 1:
                edited = json.loads(request["proposal"])
                edited["status"] = "approved"
                edited["label"] = "Owner revision."
                return {
                    "action": "accept",
                    "content": {
                        "disposition": "edited",
                        "edited_proposal": json.dumps(edited, sort_keys=True, separators=(",", ":")),
                    },
                }
            self.assertIn("Owner revision.", parameters["message"])
            self.assertIn('"status":"proposed"', parameters["message"])
            return {"action": "accept", "content": {"disposition": "approved"}}

        result = server.call_tool("frameshift_confirm", {"request_id": request["id"]}, elicit)
        self.assertEqual(result["outcome"], "confirmed", result)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["events"], [])

    def test_a_different_live_client_identity_cannot_elicit(self) -> None:
        server, request = self.server()
        server.initialize(
            {"elicitation": {"form": {}}},
            {"name": "different-client", "version": "2.1.265"},
        )
        calls = []
        result = server.call_tool("frameshift_confirm", {"request_id": request["id"]}, calls.append)
        self.assertEqual(result["code"], "unsupported_configuration")
        self.assertEqual(calls, [])

    def test_a_validated_profile_inside_the_agent_workspace_is_refused(self) -> None:
        refusal = approval_configuration_refusal(
            PROFILE,
            [ROOT / "evals" / "fixtures" / "confirmation" / "operator-attestation.json"],
            ROOT,
        )
        self.assertIn("outside", refusal)

    def test_workspace_protection_does_not_depend_on_the_launch_directory(self) -> None:
        protected = ROOT / "evals" / "fixtures" / "confirmation" / "operator-attestation.json"
        launch_directory = ROOT / "frameshift"
        refusal = approval_configuration_refusal(PROFILE, [protected], ROOT)
        self.assertIn("outside", refusal)
        self.assertNotEqual(protected.parent, launch_directory)

    def test_stdio_reports_a_confirmed_disposition_as_tool_success(self) -> None:
        server, request = self.server()
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"elicitation": {"form": {}}},
                    "clientInfo": {"name": "claude-code", "version": "2.1.265"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "frameshift_confirm",
                    "arguments": {"request_id": request["id"]},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"action": "accept", "content": {"disposition": "approved"}},
            },
        ]
        input_stream = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
        output_stream = io.StringIO()

        run_stdio(server, input_stream, output_stream)

        output = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        tool_response = next(message for message in output if message.get("id") == 11)
        self.assertFalse(tool_response["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
