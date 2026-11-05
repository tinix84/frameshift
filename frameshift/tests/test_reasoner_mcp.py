#!/usr/bin/env python3
"""The reasoner's MCP server: reasoner-safe commands over the shared store (#286).

The person drives the GUI's coordinator; the reasoner drives this server. Both
write one event log per session. The server exposes no command that decides
something, and the actor of every write comes from its configuration.
"""

from __future__ import annotations

import ast
import contextlib
import io
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import LOCAL_STORE, gui_vocabulary, reasoner_coordinator, reasoner_parser  # noqa: E402
from frameshift.mcp.reasoner_server import PROTOCOL_VERSION, ReasonerMcpServer, run_stdio  # noqa: E402
from frameshift.orchestration.api import CommandRefused  # noqa: E402
from frameshift.tests.test_sessions import REQUEST, _alternative, _frame, approve, coordinator  # noqa: E402

RUNTIME = {"id": "reasoner_local", "kind": "runtime"}

READ_TOOLS = {"frameshift_list_sessions", "frameshift_get_session", "frameshift_get_history"}
WRITE_TOOLS = {
    "frameshift_add_statement",
    "frameshift_propose_frame",
    "frameshift_record_rung",
    "frameshift_add_node",
    "frameshift_add_edge",
    "frameshift_raise_challenge",
}
# The person's commands (ADR-0028 to ADR-0032, ADR-0022). None may be a tool.
PERSON_ONLY = (
    "add_operator_statement",
    "supersede_statement",
    "activate_frame",
    "withdraw_frame",
    "answer_challenge",
    "concede_challenge",
    "park_line",
    "reopen_line",
    "prepare_gate",
    "confirm",
    "open_session",
    "admit_result",
    "correct_classification",
)
PERSON_WORDS = ("operator", "supersede", "activate", "withdraw", "answer", "concede", "park", "reopen", "gate", "confirm", "approv")


class Tandem(unittest.TestCase):
    """The person opens a session in the GUI's store; the reasoner works on it."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = Path(self._dir.name)
        self.person = coordinator(self.store)
        self.sid = self.person.open_session(title="", request=REQUEST)["state"]["id"]
        counter = itertools.count(1)
        self.reasoner = reasoner_coordinator(
            self.store, RUNTIME, clock=lambda: "2026-11-05T09:00:00Z", new_suffix=lambda: f"r{next(counter):04d}"
        )
        self.server = ReasonerMcpServer(self.reasoner, RUNTIME, vocabulary=gui_vocabulary())

    def tearDown(self) -> None:
        self._dir.cleanup()

    def revision(self) -> int:
        return self.person.state(self.sid)["revision"]

    def call(self, name: str, **arguments) -> dict:
        return self.server.call_tool(name, arguments)

    def write(self, name: str, **arguments) -> dict:
        return self.call(name, session_id=self.sid, expected_revision=self.revision(), **arguments)

    def refused(self, name: str, **arguments) -> dict:
        before = len(self.person.history(self.sid))
        outcome = self.call(name, **arguments)
        self.assertEqual(outcome["outcome"], "refused", outcome)
        self.assertNotIn("events", outcome, "a refusal never looks like a commit")
        self.assertEqual(len(self.person.history(self.sid)), before, "a refused tool call writes nothing")
        return outcome

    def seal_intake(self) -> None:
        result = self.person.manual_framing_result(
            self.sid, [{"statement_id": "stmt_001", "primary_role": "proposal", "secondary_roles": ["need"]}]
        )
        self.person.admit_result(self.sid, result)
        self.write("frameshift_add_statement", text="Pack cost per usable kWh meets the target.", primary_role="outcome")
        approve(self.person, self.person.prepare_gate(self.sid, gate="intake_correction", target_id="stmt_001"))

    def to_causal(self) -> None:
        self.seal_intake()
        self.write("frameshift_propose_frame", frame=_frame())
        self.write("frameshift_propose_frame", frame=_alternative())
        self.person.activate_frame(self.sid, frame_id="frame_001", expected_revision=self.revision())
        approve(self.person, self.person.prepare_gate(self.sid, gate="frame_selection", target_id="frame_001"))


class TheToolListHoldsNoDecision(Tandem):
    def tools(self) -> dict:
        return {tool["name"]: tool for tool in self.server.list_tools()}

    def test_the_tools_are_the_three_reads_and_the_six_reasoner_safe_writes(self) -> None:
        self.assertEqual(set(self.tools()), READ_TOOLS | WRITE_TOOLS)

    def test_no_person_command_is_a_tool(self) -> None:
        for name in self.tools():
            for command in PERSON_ONLY:
                with self.subTest(tool=name, command=command):
                    self.assertNotIn(command, name)
            for word in PERSON_WORDS:
                with self.subTest(tool=name, word=word):
                    self.assertNotIn(word, name)

    def test_every_write_requires_the_revision_it_was_formed_against(self) -> None:
        for name in WRITE_TOOLS:
            with self.subTest(tool=name):
                schema = self.tools()[name]["inputSchema"]
                self.assertIn("expected_revision", schema["required"])
                self.assertEqual(schema["properties"]["expected_revision"]["type"], "integer")

    def test_no_tool_takes_an_actor_or_an_owner(self) -> None:
        for name, tool in self.tools().items():
            with self.subTest(tool=name):
                self.assertFalse(tool["inputSchema"]["additionalProperties"])
                text = json.dumps(tool["inputSchema"])
                self.assertNotIn('"actor"', text)
                self.assertNotIn('"owner"', text)

    def test_the_schemas_offer_the_published_vocabulary(self) -> None:
        vocabulary = gui_vocabulary()
        node = self.tools()["frameshift_add_node"]["inputSchema"]["properties"]["node"]["properties"]
        self.assertEqual(node["type"]["enum"], vocabulary["node_types"])
        self.assertEqual(node["status"]["enum"], ["draft", "proposed"])

    def test_the_server_imports_only_contracts_and_the_api(self) -> None:
        """ADR-0015: `mcp` may import `contracts` and `orchestration.api` only."""
        allowed = {"frameshift.contracts", "frameshift.orchestration.api"}
        path = ROOT / "frameshift" / "mcp" / "reasoner_server.py"
        offenders = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            offenders += [name for name in names if name.startswith("frameshift") and name not in allowed]
        self.assertEqual(offenders, [])


class TheReasonerWritesTheSharedLog(Tandem):
    def test_a_statement_is_committed_assumed_and_the_person_sees_it(self) -> None:
        outcome = self.write("frameshift_add_statement", text="Cells are 60% of pack cost.", primary_role="observation")
        self.assertEqual((outcome["outcome"], outcome["revision"]), ("committed", 1))
        (event,) = outcome["events"]
        self.assertEqual((event["type"], event["payload"]["provenance"]["kind"]), ("statement.added", "assumed"))
        self.assertEqual(self.person.state(self.sid)["statements"][-1]["text"], "Cells are 60% of pack cost.")

    def test_an_observed_statement_is_refused(self) -> None:
        """ADR-0028: only the person's boundary records an observed statement."""
        outcome = self.refused(
            "frameshift_add_statement", session_id=self.sid, expected_revision=self.revision(),
            text="I saw it.", primary_role="observation",
            provenance={"kind": "observed", "source_ids": []},
        )
        self.assertEqual(outcome["code"], "invariant_violation")

    def test_a_stale_revision_is_refused_with_its_code(self) -> None:
        outcome = self.refused(
            "frameshift_add_statement", session_id=self.sid, expected_revision=7, text="Late.", primary_role="observation"
        )
        self.assertEqual(outcome["code"], "revision_conflict")
        self.assertIn("re-read", outcome["detail"])

    def test_a_missing_revision_or_an_extra_argument_is_refused_as_schema_invalid(self) -> None:
        for arguments in (
            {"session_id": self.sid, "text": "No revision.", "primary_role": "observation"},
            {"session_id": self.sid, "expected_revision": 0, "text": "Extra.", "primary_role": "observation", "actor": {"id": "user_lead_eng", "kind": "human"}},
            {"session_id": self.sid, "expected_revision": "0", "text": "String revision.", "primary_role": "observation"},
        ):
            with self.subTest(arguments=sorted(arguments)):
                self.assertEqual(self.refused("frameshift_add_statement", **arguments)["code"], "schema_invalid")

    def test_an_unknown_tool_is_refused(self) -> None:
        self.assertEqual(self.refused("frameshift_answer_challenge", session_id=self.sid)["code"], "schema_invalid")

    def test_a_frame_and_a_rung_are_proposed_in_framing(self) -> None:
        self.seal_intake()
        frame = self.write("frameshift_propose_frame", frame=_frame())
        self.assertEqual(frame["events"][0]["payload"]["status"], "proposed")
        rung = {"abstraction_level": "product", "outcome": "Cheaper usable kWh.", "scope": "The pack.", "system_boundary": "product", "loss": "Cell chemistry drops out."}
        recorded = self.write("frameshift_record_rung", rung=rung)
        self.assertEqual(recorded["events"][0]["type"], "ladder.rung.recorded")
        again = self.write("frameshift_record_rung", rung_id="rung_001", rung=dict(rung, outcome="Cheaper kWh over life."))
        self.assertEqual(self.person.state(self.sid)["ladder"][0]["outcome"], again["events"][0]["payload"]["outcome"])

    def test_a_node_an_edge_and_a_challenge_in_causal(self) -> None:
        self.to_causal()
        self.write("frameshift_add_node", node={"type": "hypothesis", "label": "Cell price dominates."})
        self.write("frameshift_add_node", node={"type": "evidence", "label": "Quote at volume.", "status": "draft"})
        edge = self.write("frameshift_add_edge", edge={"source": "node_002", "target": "node_001", "type": "causes"})
        self.assertEqual(edge["events"][0]["payload"]["owner"], RUNTIME, "the reasoner owns the causal claim it makes")
        challenge = self.write("frameshift_raise_challenge", target_id="node_001", objection="One quote is one supplier.")
        self.assertEqual(challenge["events"][0]["payload"]["actor"], RUNTIME)
        self.assertEqual(self.person.state(self.sid)["challenges"][0]["status"], "open")

    def test_a_decided_node_status_is_refused(self) -> None:
        self.to_causal()
        outcome = self.refused(
            "frameshift_add_node", session_id=self.sid, expected_revision=self.revision(),
            node={"type": "hypothesis", "label": "Settled.", "status": "approved"},
        )
        self.assertEqual(outcome["code"], "invariant_violation")


class TheReasonerReads(Tandem):
    def test_the_sessions_are_listed(self) -> None:
        listed = self.call("frameshift_list_sessions")
        self.assertEqual([s["id"] for s in listed["sessions"]], [self.sid])

    def test_a_session_reads_with_its_derived_grounding_and_without_its_history(self) -> None:
        self.to_causal()
        self.write("frameshift_add_node", node={"type": "hypothesis", "label": "Cell price dominates."})
        read = self.call("frameshift_get_session", session_id=self.sid)
        self.assertEqual(read["state"]["revision"], self.revision())
        self.assertIn("node_001", read["derived"]["grounding"]["nodes"])
        self.assertNotIn("history", read)
        for local in ("held", "pending_confirmations"):
            self.assertNotIn(local, read["derived"], "another process's memory is not this server's to report")

    def test_an_unknown_session_is_refused(self) -> None:
        self.assertEqual(self.refused("frameshift_get_session", session_id="sess_missing")["code"], "invariant_violation")

    def test_the_history_is_bounded_and_pages_forward(self) -> None:
        for number in range(5):
            self.write("frameshift_add_statement", text=f"Fact {number}.", primary_role="observation")
        first = self.call("frameshift_get_history", session_id=self.sid, limit=3)
        self.assertEqual([e["sequence"] for e in first["events"]], [1, 2, 3])
        self.assertEqual((first["next_after"], first["total"]), (3, 7))
        rest = self.call("frameshift_get_history", session_id=self.sid, after_sequence=first["next_after"], limit=200)
        self.assertEqual([e["sequence"] for e in rest["events"]], [4, 5, 6, 7])
        self.assertIsNone(rest["next_after"])
        self.assertEqual(self.refused("frameshift_get_history", session_id=self.sid, limit=201)["code"], "schema_invalid")


class OverStdio(Tandem):
    def exchange(self, *messages) -> list[dict]:
        lines = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
        out = io.StringIO()
        run_stdio(self.server, io.StringIO(lines), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_initialize_list_and_call(self) -> None:
        replies = self.exchange(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "frameshift_add_statement", "arguments": {"session_id": self.sid, "expected_revision": 0, "text": "Cells dominate.", "primary_role": "observation"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "frameshift_add_statement", "arguments": {"session_id": self.sid, "expected_revision": 0, "text": "Stale.", "primary_role": "observation"}}},
        )
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4], "a notification gets no reply")
        init = replies[0]["result"]
        self.assertEqual(init["protocolVersion"], "2025-11-25")
        self.assertEqual(init["capabilities"], {"tools": {}})
        self.assertIn("expected_revision", init["instructions"])
        self.assertEqual({t["name"] for t in replies[1]["result"]["tools"]}, READ_TOOLS | WRITE_TOOLS)
        committed, stale = replies[2]["result"], replies[3]["result"]
        self.assertFalse(committed["isError"])
        self.assertEqual(json.loads(committed["content"][0]["text"]), committed["structuredContent"])
        self.assertEqual(committed["structuredContent"]["outcome"], "committed")
        self.assertTrue(stale["isError"])
        self.assertEqual(stale["structuredContent"]["code"], "revision_conflict")

    def test_a_line_that_is_not_json_and_an_unknown_method_are_errors_not_crashes(self) -> None:
        replies = self.exchange("{not json", {"jsonrpc": "2.0", "id": 9, "method": "resources/list"}, {"jsonrpc": "2.0", "id": 10, "method": "ping"})
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual((replies[1]["id"], replies[1]["error"]["code"]), (9, -32601))
        self.assertEqual(replies[2], {"jsonrpc": "2.0", "id": 10, "result": {}})


class TheReasonerIsAssembledInBootstrap(unittest.TestCase):
    def test_the_default_store_is_the_guis(self) -> None:
        args = reasoner_parser().parse_args([])
        self.assertEqual(args.store, None)
        self.assertEqual(LOCAL_STORE, Path(".frameshift") / "sessions")

    def test_the_actor_is_a_runtime_and_cannot_approve(self) -> None:
        with tempfile.TemporaryDirectory() as store:
            co = reasoner_coordinator(Path(store), RUNTIME)
            self.assertEqual(co.operator, RUNTIME)
            person = coordinator(Path(store))
            sid = person.open_session(title="", request=REQUEST)["state"]["id"]
            person.admit_result(sid, person.manual_framing_result(sid, [{"statement_id": "stmt_001", "primary_role": "outcome"}]))
            # Even through the coordinator, which the server never exposes,
            # its profile is not validated, so no confirmation can bind.
            with self.assertRaises(CommandRefused) as refused:
                approve(co, co.prepare_gate(sid, gate="intake_correction", target_id="stmt_001"))
            self.assertIn(refused.exception.code, {"unsupported_configuration", "approval_required"})
            self.assertEqual(co.state(sid)["approvals"], [])

    def test_an_actor_id_outside_the_id_pattern_is_refused_at_start(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            reasoner_parser().parse_args(["--actor", "has space"])


if __name__ == "__main__":
    unittest.main()
