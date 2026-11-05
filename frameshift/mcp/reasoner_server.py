"""A stdio MCP server for the reasoner's domain commands (#286, ADR-0009).

The reasoner is the MCP client: FrameShift calls no model. This server lets it
read a session and propose into it through the session coordinator, over the
same event log the manual GUI writes. The person judges in the GUI.

What it exposes is decided here, by omission. A reasoner may add an assumed or
earned statement, propose a frame, record a rung, offer a node or an edge, and
raise a challenge. Each of those decides nothing. It never exposes a command
that decides: the person's own words (ADR-0028), supersession (ADR-0029),
frame activation or withdrawal (ADR-0030), answering or conceding a challenge
(ADR-0031), parking or reopening a line (ADR-0032), or any gate or approval.

The actor is the server's configuration, never a tool argument. Every write
carries the revision its caller read, and a refusal comes back with its
published code and is never shaped like a commit.

Like `confirmation_server`, this module translates protocol values into
application calls and imports `contracts` and `orchestration.api` only
(ADR-0015). Bootstrap owns the store and the actor.
"""

from __future__ import annotations

import copy
import json
from typing import TextIO

from frameshift.contracts import errors
from frameshift.orchestration.api import CommandRefused, SessionCoordinator

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "frameshift-reasoner", "version": "0.1.0"}
HISTORY_DEFAULT, HISTORY_MAX = 50, 200
SESSIONS_MAX = 200
# Derived values that live in one process's memory. The GUI's held
# proposals and pending confirmations are not this process's to report.
PROCESS_LOCAL = ("held", "pending_confirmations")

INSTRUCTIONS = (
    "FrameShift records an engineering problem's decision path. You propose; the person decides "
    "in the FrameShift GUI. Read a session before you write, and pass the revision you read as "
    "expected_revision. A revision_conflict means the person or another writer moved first: read "
    "again and decide whether your write still makes sense. You cannot approve gates, activate or "
    "withdraw frames, answer or concede challenges, park lines, or record the person's own words."
)


class ReasonerMcpServer:
    def __init__(self, coordinator: SessionCoordinator, actor: dict, *, vocabulary: dict) -> None:
        self._co = coordinator
        self._actor = copy.deepcopy(actor)
        self._tools = _tools(vocabulary)
        self._schemas = {tool["name"]: tool["inputSchema"] for tool in self._tools}

    def list_tools(self) -> list[dict]:
        return copy.deepcopy(self._tools)

    def call_tool(self, name, arguments) -> dict:
        schema = self._schemas.get(name)
        if schema is None:
            return _refused(errors.SCHEMA_INVALID, f"unknown tool {name!r}")
        if arguments is None:
            arguments = {}
        problem = _argument_problem(schema, arguments)
        if problem:
            return _refused(errors.SCHEMA_INVALID, problem)
        try:
            return getattr(self, "_" + name.removeprefix("frameshift_"))(**arguments)
        except CommandRefused as refused:
            return _refused(refused.code, refused.detail)
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            # A nested value of the wrong shape fails while the command builds
            # its payload, before anything is committed.
            return _refused(errors.SCHEMA_INVALID, f"malformed argument: {exc}")

    # ------------------------------------------------------------------ reads

    def _list_sessions(self) -> dict:
        found = self._co.sessions()
        return {"outcome": "read", "sessions": found[:SESSIONS_MAX], "truncated": len(found) > SESSIONS_MAX}

    def _get_session(self, session_id: str) -> dict:
        view = self._co.view(session_id)
        derived = {key: value for key, value in view["derived"].items() if key not in PROCESS_LOCAL}
        return {"outcome": "read", "state": view["state"], "derived": derived}

    def _get_history(self, session_id: str, after_sequence: int = 0, limit: int = HISTORY_DEFAULT) -> dict:
        history = self._co.history(session_id)
        if not history:
            raise CommandRefused(errors.INVARIANT_VIOLATION, f"no session {session_id!r}")
        page = [event for event in history if event["sequence"] > after_sequence][:limit]
        more = bool(page) and page[-1]["sequence"] < history[-1]["sequence"]
        return {
            "outcome": "read",
            "session_id": session_id,
            "events": page,
            "next_after": page[-1]["sequence"] if more else None,
            "total": len(history),
        }

    # ----------------------------------------------------------------- writes

    def _write(self, command, session_id: str, expected_revision: int, **arguments) -> dict:
        before = len(self._co.history(session_id))
        view = command(session_id, expected_revision=expected_revision, **arguments)
        return _committed(view, expected_revision, before)

    def _add_statement(self, session_id, text, primary_role, expected_revision, provenance=None) -> dict:
        return self._write(
            self._co.add_statement, session_id, expected_revision, text=text, primary_role=primary_role, provenance=provenance
        )

    def _propose_frame(self, session_id, frame, expected_revision) -> dict:
        return self._write(self._co.propose_frame, session_id, expected_revision, frame=frame)

    def _record_rung(self, session_id, rung, expected_revision, rung_id=None) -> dict:
        return self._write(self._co.record_rung, session_id, expected_revision, rung=rung, rung_id=rung_id)

    def _add_node(self, session_id, node, expected_revision) -> dict:
        return self._write(self._co.add_node, session_id, expected_revision, node=node)

    def _add_edge(self, session_id, edge, expected_revision) -> dict:
        return self._write(self._co.add_edge, session_id, expected_revision, edge=edge)

    def _raise_challenge(self, session_id, target_id, objection, expected_revision) -> dict:
        actor = copy.deepcopy(self._actor)
        return self._write(
            self._co.raise_challenge, session_id, expected_revision, target_id=target_id, objection=objection, actor=actor
        )


def _committed(view: dict, expected_revision: int, before: int) -> dict:
    """The events of exactly this commit, found by its revision, not by position.

    Another process may commit between this write and the view that follows
    it, so the tail of the history is not necessarily this commit. A later
    commit carries its revision on its last event, so this one starts after
    the event that carries the revision it was formed against. Creation
    carries revision 0 on its first event instead (ADR-0013), so the commit
    after it starts at `before`, the history's length when the command was
    formed: had that history been anything but the creation commit, the
    command would have been refused as stale.
    """
    revision = expected_revision + 1
    history = view["history"]
    end = next(index for index, event in enumerate(history) if event.get("revision") == revision)
    if expected_revision == 0:
        start = before
    else:
        start = 1 + next(index for index, event in enumerate(history) if event.get("revision") == expected_revision)
    events = [{key: event[key] for key in ("sequence", "type", "payload")} for event in history[start : end + 1]]
    return {
        "outcome": "committed",
        "session_id": view["state"]["id"],
        "revision": revision,
        "session_revision": view["state"]["revision"],
        "events": events,
    }


def _refused(code: str, detail: str) -> dict:
    return {"outcome": "refused", "code": code, "detail": detail}


# ---------------------------------------------------------------- the tools

_JSON_TYPES = {"string": str, "integer": int, "object": dict, "array": list}


def _argument_problem(schema: dict, arguments) -> str | None:
    """Top-level shape only. The coordinator validates content on commit."""
    if not isinstance(arguments, dict):
        return "tool arguments must be an object"
    unknown = sorted(set(arguments) - set(schema["properties"]))
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    missing = [name for name in schema["required"] if name not in arguments]
    if missing:
        return f"missing argument(s): {', '.join(missing)}"
    for name, value in arguments.items():
        spec = schema["properties"][name]
        expected = _JSON_TYPES[spec["type"]]
        # bool is an int in Python; a revision of `true` is not a revision.
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            return f"{name} must be of type {spec['type']}"
        if expected is int and not spec.get("minimum", value) <= value <= spec.get("maximum", value):
            return f"{name} must be between {spec.get('minimum')} and {spec.get('maximum')}"
    return None


def _tools(vocabulary: dict) -> list[dict]:
    session = {"type": "string", "description": "A session id, as frameshift_list_sessions returns it."}
    revision = {
        "type": "integer",
        "minimum": 0,
        "description": "The session revision you read. A stale value is refused with revision_conflict.",
    }
    provenance = {
        "type": "object",
        "description": (
            "Optional. kind is sourced (cite an art_ id), inferred (cite ids in this session), or assumed. "
            "Never observed: only the person's boundary records the person's words. Omit for assumed."
        ),
        "properties": {
            "kind": {"type": "string", "enum": ["sourced", "inferred", "assumed", "unknown"]},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"},
        },
    }
    texts = {"type": "array", "items": {"type": "string"}}
    frame = {
        "question": {"type": "string"},
        "outcome": {"type": "string"},
        "abstraction_level": {"type": "string", "enum": vocabulary["abstraction_levels"]},
        "system_boundary": {"type": "string", "enum": vocabulary["system_boundaries"]},
        **{key: texts for key in ("included", "excluded", "success_measures", "constraints", "assumptions", "open_questions")},
    }
    rung = {
        "abstraction_level": {"type": "string", "enum": vocabulary["abstraction_levels"]},
        "outcome": {"type": "string"},
        "scope": {"type": "string"},
        "system_boundary": {"type": "string", "enum": vocabulary["system_boundaries"]},
        "success_measures": texts,
        "assumptions": texts,
        "loss": {"type": "string", "description": "What drops out of view at this level."},
        "provenance": provenance,
    }
    offered = {"type": "string", "enum": ["draft", "proposed"], "description": "Default proposed. A decided status is the person's."}
    confidence = {"type": "string", "enum": vocabulary["confidence"]}
    node = {
        "type": {"type": "string", "enum": vocabulary["node_types"]},
        "label": {"type": "string"},
        "description": {"type": "string"},
        "status": offered,
        "confidence": confidence,
        "provenance": provenance,
        "source_ids": {"type": "array", "items": {"type": "string"}, "description": "Sources of an assumed node; or use provenance."},
        "extensions": {"type": "object"},
    }
    edge = {
        "source": {"type": "string", "description": "A node id."},
        "target": {"type": "string", "description": "A node id."},
        "type": {"type": "string", "enum": vocabulary["edge_types"]},
        "status": offered,
        "confidence": confidence,
        "provenance": provenance,
        "extensions": {"type": "object"},
    }

    def tool(name, title, description, properties, required, *, writes=False):
        properties = dict(properties)
        required = list(required)
        if writes:
            properties["expected_revision"] = revision
            required.append("expected_revision")
        return {
            "name": name,
            "title": title,
            "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
            "annotations": {"readOnlyHint": not writes, "destructiveHint": False, "idempotentHint": not writes},
        }

    def obj(properties, required=()):
        return {"type": "object", "properties": properties, "required": list(required)}

    return [
        tool("frameshift_list_sessions", "List sessions", "The sessions in the shared store, with phase and revision.", {}, []),
        tool(
            "frameshift_get_session",
            "Read a session",
            "One session's folded state and derived values (gates, frame set, ladder order, grounding). "
            "Read this before a write and pass state.revision as expected_revision.",
            {"session_id": session},
            ["session_id"],
        ),
        tool(
            "frameshift_get_history",
            "Read a session's events",
            f"The session's event history in order, at most {HISTORY_MAX} events a call. "
            "Pass next_after as after_sequence to read on.",
            {
                "session_id": session,
                "after_sequence": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": HISTORY_MAX},
            },
            ["session_id"],
        ),
        tool(
            "frameshift_add_statement",
            "Add a statement",
            "Intake only. Add a statement you classified. It is assumed unless its provenance earns more. "
            "It is never the person's own words.",
            {
                "session_id": session,
                "text": {"type": "string"},
                "primary_role": {"type": "string", "enum": vocabulary["statement_roles"]},
                "provenance": provenance,
            },
            ["session_id", "text", "primary_role"],
            writes=True,
        ),
        tool(
            "frameshift_propose_frame",
            "Propose a candidate frame",
            "Framing only. Add a candidate frame, proposed. The person activates and selects frames.",
            {"session_id": session, "frame": obj(frame, ("question", "outcome", "abstraction_level", "system_boundary"))},
            ["session_id", "frame"],
            writes=True,
        ),
        tool(
            "frameshift_record_rung",
            "Record a ladder rung",
            "Framing only. Record one rung of the abstraction ladder, one per level. "
            "Pass rung_id to record that rung again, whole.",
            {
                "session_id": session,
                "rung": obj(rung, ("abstraction_level", "outcome", "scope", "system_boundary", "loss")),
                "rung_id": {"type": "string"},
            },
            ["session_id", "rung"],
            writes=True,
        ),
        tool(
            "frameshift_add_node",
            "Offer a graph node",
            "Causal only. Offer a node as draft or proposed.",
            {"session_id": session, "node": obj(node, ("type", "label"))},
            ["session_id", "node"],
            writes=True,
        ),
        tool(
            "frameshift_add_edge",
            "Offer a graph edge",
            "Causal only. Offer an edge between two nodes as draft or proposed.",
            {"session_id": session, "edge": obj(edge, ("source", "target", "type"))},
            ["session_id", "edge"],
            writes=True,
        ),
        tool(
            "frameshift_raise_challenge",
            "Raise a challenge",
            "Record a doubt about one graph node or edge, in any phase. Only the person answers or concedes it.",
            {"session_id": session, "target_id": {"type": "string"}, "objection": {"type": "string"}},
            ["session_id", "target_id", "objection"],
            writes=True,
        ),
    ]


# ------------------------------------------------------------------ stdio


def run_stdio(server: ReasonerMcpServer, input_stream: TextIO, output_stream: TextIO) -> None:
    """Serve newline-delimited MCP JSON-RPC over stdio until the input closes."""

    def write(message: dict) -> None:
        output_stream.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()

    for line in input_stream:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"parse error: {exc.msg}"}})
            continue
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue  # a notification, or a response this server never asked for
        rpc_id, method = message["id"], message["method"]
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": server.list_tools()}
        elif method == "tools/call":
            outcome = server.call_tool(params.get("name"), params.get("arguments", {}))
            result = {
                "content": [{"type": "text", "text": json.dumps(outcome, ensure_ascii=False, sort_keys=True)}],
                "structuredContent": outcome,
                "isError": outcome["outcome"] == "refused",
            }
        else:
            write({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"method not found: {method}"}})
            continue
        write({"jsonrpc": "2.0", "id": rpc_id, "result": result})
