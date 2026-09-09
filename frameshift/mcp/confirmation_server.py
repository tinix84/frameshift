"""A narrow MCP server for Claude Code's native confirmation dialog (#205).

This module deliberately uses only JSON-RPC framing from the MCP protocol. The
repository does not yet carry the SDK dependency owned by #172; keeping this
slice here preserves the boundary and makes the actual-client path executable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from frameshift.orchestration.api import ConfirmationWorkflow

PROTOCOL_VERSION = "2025-11-25"
TOOL_NAME = "frameshift_confirm"


class ConfirmationMcpServer:
    def __init__(
        self,
        workflow: ConfirmationWorkflow,
        attestation_loader: Callable[[], dict],
        clock: Callable[[], str],
    ) -> None:
        self._workflow = workflow
        self._attestation_loader = attestation_loader
        self._clock = clock
        self._form_elicitation = False

    def initialize(self, client_capabilities: dict) -> None:
        elicitation = client_capabilities.get("elicitation")
        self._form_elicitation = isinstance(elicitation, dict) and "form" in elicitation

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
        request = self._workflow.pending(arguments["request_id"])
        if request is None:
            return _pending("approval_stale", "no such pending confirmation request")

        native = elicit(elicitation_parameters(request))
        # Request identity is supplied by the server. A client or model cannot
        # redirect its answer by returning replacement identity fields.
        response = {
            "request_id": request["id"],
            "request_digest": request["request_digest"],
            "action": native.get("action"),
            "content": native.get("content"),
        }
        return self._workflow.complete(
            request["id"],
            response,
            self._attestation_loader(),
            confirmed_at=self._clock(),
        )


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
            server.initialize(params.get("capabilities", {}))
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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _pending(code: str, detail: str) -> dict:
    return {"outcome": "pending", "code": code, "detail": detail, "events": []}


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve one pending FrameShift confirmation over MCP")
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--transition", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--request-id", default="confirm_live_001")
    args = parser.parse_args()

    profile = _load(args.profile)
    workflow = ConfirmationWorkflow(_load(args.session), profile)
    workflow.prepare(_load(args.transition), _load(args.attestation), request_id=args.request_id)
    server = ConfirmationMcpServer(workflow, lambda: _load(args.attestation), _utc_now)
    run_stdio(server, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
