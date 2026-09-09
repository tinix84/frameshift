"""A narrow MCP server for Claude Code's native confirmation dialog (#205).

This module translates MCP protocol values into provider-neutral application
values. Bootstrap owns files, configuration, and construction.
"""

from __future__ import annotations

import json
from typing import Callable, TextIO

from frameshift.orchestration.api import ConfirmationWorkflow

PROTOCOL_VERSION = "2025-11-25"
TOOL_NAME = "frameshift_confirm"


class ConfirmationMcpServer:
    def __init__(
        self,
        workflow: ConfirmationWorkflow,
        attestation_loader: Callable[[], dict],
        profile_loader: Callable[[], dict],
        clock: Callable[[], str],
    ) -> None:
        self._workflow = workflow
        self._attestation_loader = attestation_loader
        self._profile_loader = profile_loader
        self._clock = clock
        self._form_elicitation = False
        self._client_info = {}

    def initialize(self, client_capabilities: dict, client_info: dict | None = None) -> None:
        elicitation = client_capabilities.get("elicitation")
        self._form_elicitation = isinstance(elicitation, dict) and "form" in elicitation
        self._client_info = dict(client_info or {})

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": TOOL_NAME,
                "title": "Review a pending FrameShift proposal",
                "description": (
                    "Ask the human operator to review one already-pending proposal in the "
                    "client's native confirmation dialog. Tool arguments cannot approve it."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["request_id"],
                    "properties": {"request_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, elicit: Callable[[dict], dict]) -> dict:
        if name != TOOL_NAME:
            return _pending("schema_invalid", f"unknown tool {name!r}")
        if not isinstance(arguments, dict) or set(arguments) != {"request_id"}:
            return _pending("schema_invalid", "tool input must contain only request_id")
        if not self._form_elicitation:
            return _pending(
                "unsupported_configuration",
                "client did not declare native form elicitation support",
            )
        attestation = self._attestation_loader()
        profile = self._profile_loader()
        if (
            self._client_info.get("name") != profile.get("client_id")
            or self._client_info.get("version") != profile.get("client_version")
            or self._client_info.get("name") != attestation.get("client_id")
            or self._client_info.get("version") != attestation.get("client_version")
        ):
            return _pending(
                "unsupported_configuration",
                "live MCP client identity does not match the attested approval profile",
            )
        request = self._workflow.pending(arguments["request_id"])
        if request is None:
            return _pending("approval_stale", "no such pending confirmation request")

        for _ in range(5):
            native = elicit(elicitation_parameters(request))
            response = translate_elicitation_response(request, native)
            result = self._workflow.complete(
                request["id"],
                response,
                self._attestation_loader(),
                self._profile_loader(),
                confirmed_at=self._clock(),
            )
            if result["outcome"] != "revised":
                return result
            request = result["confirmation_request"]
        return _pending("approval_required", "too many consecutive edits; proposal remains pending")


def elicitation_parameters(request: dict) -> dict:
    """Translate an exact canonical request into MCP form elicitation."""
    dispositions = request["permitted_dispositions"]
    message = "\n".join(
        [
            "FrameShift requires human review of this exact proposal.",
            f"Confirmation request: {request['id']}",
            f"Request digest: {request['request_digest']}",
            f"Session: {request['session_id']}",
            f"Session revision: {request['session_revision']}",
            f"Gate: {request['gate']}",
            f"Target: {request['target_id']}",
            f"Target digest: {request['target_digest']}",
            f"Actor authority: {request['actor']['id']} ({request['actor'].get('role', '')})",
            "Permitted dispositions: " + ", ".join(dispositions),
            "Exact proposal:",
            request["proposal"],
            "Selecting edited requires edited_proposal and never approves the edit.",
        ]
    )
    return {
        "mode": "form",
        "message": message,
        "requestedSchema": {
            "type": "object",
            "required": ["disposition"],
            "properties": {
                "disposition": {
                    "type": "string",
                    "title": "Disposition",
                    "enum": dispositions,
                },
                "edited_proposal": {
                    "type": "string",
                    "title": "Edited proposal JSON (required only when edited)",
                },
            },
            "additionalProperties": False,
        },
    }


def translate_elicitation_response(request: dict, native: dict) -> dict:
    """Keep MCP action/content vocabulary at the protocol boundary."""
    action = native.get("action")
    content = native.get("content") if isinstance(native.get("content"), dict) else {}
    status = {"accept": "submitted", "decline": "declined", "cancel": "cancelled"}.get(
        action,
        "cancelled",
    )
    return {
        "request_id": request["id"],
        "request_digest": request["request_digest"],
        "status": status,
        "disposition": content.get("disposition") if status == "submitted" else None,
        "edited_proposal": content.get("edited_proposal") if status == "submitted" else None,
    }


def run_stdio(server: ConfirmationMcpServer, input_stream: TextIO, output_stream: TextIO) -> None:
    """Serve newline-delimited MCP JSON-RPC over stdio."""
    next_request_id = 1

    def write(message: dict) -> None:
        output_stream.write(json.dumps(message, separators=(",", ":")) + "\n")
        output_stream.flush()

    def elicit(parameters: dict) -> dict:
        nonlocal next_request_id
        request_id = next_request_id
        next_request_id += 1
        write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "elicitation/create",
                "params": parameters,
            }
        )
        while True:
            line = input_stream.readline()
            if not line:
                return {"action": "cancel", "content": None}
            incoming = json.loads(line)
            if incoming.get("id") == request_id:
                if "error" in incoming:
                    return {"action": "cancel", "content": None}
                return incoming.get("result", {"action": "cancel", "content": None})

    for line in input_stream:
        message = json.loads(line)
        method = message.get("method")
        rpc_id = message.get("id")
        if method == "initialize":
            params = message.get("params", {})
            server.initialize(params.get("capabilities", {}), params.get("clientInfo", {}))
            result = {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "frameshift-confirmation", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": server.list_tools()}
        elif method == "tools/call":
            params = message.get("params", {})
            outcome = server.call_tool(params.get("name"), params.get("arguments", {}), elicit)
            result = {
                "content": [{"type": "text", "text": json.dumps(outcome, sort_keys=True)}],
                "isError": outcome.get("outcome") not in {"accepted", "revised"},
            }
        elif rpc_id is None:
            continue
        else:
            write(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
            continue
        if rpc_id is not None:
            write({"jsonrpc": "2.0", "id": rpc_id, "result": result})


def _pending(code: str, detail: str) -> dict:
    return {"outcome": "pending", "code": code, "detail": detail, "events": []}
