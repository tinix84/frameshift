#!/usr/bin/env python3
"""Tests for parked lines (#276, ADR-0032).

A parked line is a set of graph nodes the person stops working on. Parking
is a disposition about effort, not a verdict on truth: every status stays.
Only the person parks or reopens a line.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration.api import CommandRefused  # noqa: E402
from frameshift.orchestration.grounding import propose_line  # noqa: E402
from frameshift.tests.test_sessions import OWNER, InCausal, coordinator  # noqa: E402
from frameshift.validation import session_violations  # noqa: E402

REASON = "The supplier will not quote below volume, so this line cannot be tested."


class Lines(InCausal):
    """A fact (the anchor), an inference on it, and three inferences on that one.

    node_001 (sourced) <- node_002 <- node_003 <- node_005
                                   <- node_004
    """

    def setUp(self) -> None:
        super().setUp()
        self.node("evidence", {"kind": "sourced", "source_ids": ["art_quote"]})
        for node_id, base in (("node_002", "node_001"), ("node_003", "node_002"), ("node_004", "node_002"), ("node_005", "node_003")):
            self.node("hypothesis", {"kind": "inferred", "source_ids": [base]})
            self.co.add_edge(self.sid, edge={"source": base, "target": node_id, "type": "supports"}, expected_revision=self.revision())

    def node(self, type_: str, provenance: dict) -> None:
        self.co.add_node(self.sid, node={"type": type_, "label": "A claim.", "provenance": provenance}, expected_revision=self.revision())

    def park(self, node_ids=("node_002", "node_003"), *, anchor_id="node_001", tip_ids=("node_003",), reason_code="insufficient_evidence", reason=REASON) -> dict:
        return self.co.park_line(
            self.sid,
            anchor_id=anchor_id,
            tip_ids=list(tip_ids) if isinstance(tip_ids, tuple) else tip_ids,
            node_ids=list(node_ids) if isinstance(node_ids, tuple) else node_ids,
            reason_code=reason_code,
            reason=reason,
            expected_revision=self.revision(),
        )

    def reopen(self, line_id="line_001", reason="A second supplier now quotes at volume.") -> dict:
        return self.co.reopen_line(self.sid, line_id=line_id, reason=reason, expected_revision=self.revision())

    def grounding(self, node_id: str) -> dict:
        return self.co.view(self.sid)["derived"]["grounding"]["nodes"][node_id]

    def refused(self, command, **kwargs) -> CommandRefused:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            command(**kwargs)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused command writes nothing")
        return refused.exception


class ProposeTheNodesOfALine(Lines):
    """ADR-0032: nodes on a live support path from the anchor to a tip, less shared interior nodes."""

    def proposal(self, tip_ids: list[str], anchor_id: str = "node_001") -> list[str]:
        return self.co.line_proposal(self.sid, anchor_id=anchor_id, tip_ids=tip_ids)

    def test_a_shared_interior_node_stays_live_and_the_tip_stays(self) -> None:
        self.assertEqual(self.proposal(["node_003"]), ["node_003"], "node_004 rests on node_002, so node_002 stays live")

    def test_an_interior_node_that_only_the_line_rests_on_is_proposed(self) -> None:
        self.assertEqual(self.proposal(["node_003", "node_004"]), ["node_002", "node_003", "node_004"])

    def test_the_anchor_is_never_proposed(self) -> None:
        self.assertNotIn("node_001", self.proposal(["node_005", "node_004"]))
        self.assertEqual(self.proposal(["node_005", "node_004"]), ["node_002", "node_003", "node_004", "node_005"])

    def test_a_node_above_the_tip_keeps_the_tip_and_its_path(self) -> None:
        """node_005 rests on the tip node_003; a tip stays even when a live node rests on it."""
        self.assertEqual(self.proposal(["node_003"]), ["node_003"])

    def test_proposing_writes_nothing(self) -> None:
        before = len(self.co.history(self.sid))
        self.proposal(["node_003"])
        self.assertEqual(len(self.co.history(self.sid)), before)

    def test_an_unknown_anchor_or_tip_is_refused(self) -> None:
        for anchor_id, tip_ids in (("node_099", ["node_003"]), ("node_001", ["node_099"]), ("node_001", [])):
            with self.subTest(anchor=anchor_id, tips=tip_ids):
                with self.assertRaises(CommandRefused) as refused:
                    self.proposal(tip_ids, anchor_id)
                self.assertEqual(refused.exception.code, "invariant_violation")

    def test_the_proposal_is_a_pure_function_of_the_graph(self) -> None:
        graph = self.co.state(self.sid)
        self.assertEqual(propose_line(graph, "node_001", ["node_003", "node_004"]), ["node_002", "node_003", "node_004"])


class ParkALine(Lines):
    def test_a_park_records_the_confirmed_nodes_and_keeps_every_status(self) -> None:
        graph = self.co.state(self.sid)["graph"]
        state = self.park()["state"]
        self.assertEqual(state["graph"], graph, "parking changes no node or edge")
        self.assertEqual(
            state["lines"],
            [{
                "id": "line_001", "anchor_id": "node_001", "tip_ids": ["node_003"], "node_ids": ["node_002", "node_003"],
                "reason_code": "insufficient_evidence", "reason": REASON, "actor": OWNER, "status": "parked",
            }],
        )
        event = self.co.history(self.sid)[-1]
        self.assertEqual((event["type"], event["payload"]["actor"]), ("line.parked", OWNER))
        self.assertEqual(session_violations(state), [])

    def test_a_node_that_rests_on_a_parked_node_shows_parked_ground_and_is_not_solid(self) -> None:
        self.assertEqual(self.grounding("node_005")["band"], "solid")
        self.park()
        above = self.grounding("node_005")
        self.assertEqual(above["parked"], ["node_002", "node_003"])
        self.assertEqual(above["broken"], [], "parked ground is never broken")
        self.assertEqual(above["bases"]["fact"], ["node_001"], "a parked base counts by its class")
        self.assertEqual(above["band"], "mixed")
        self.assertEqual(self.grounding("node_004")["parked"], ["node_002"])
        self.assertEqual(self.grounding("node_001")["band"], "solid", "the anchor is not parked")

    def test_a_park_is_refused_and_writes_nothing(self) -> None:
        for kwargs, naming in (
            ({"reason_code": "too_hard"}, "reason code"),
            ({"reason": "  "}, "reason"),
            ({"reason": None}, "reason"),
            ({"node_ids": ["node_001", "node_002"]}, "anchor"),
            ({"node_ids": []}, "empty"),
            ({"node_ids": ["node_099"]}, "node_099"),
            ({"anchor_id": "node_099"}, "node_099"),
            ({"tip_ids": ["node_099"]}, "node_099"),
            ({"tip_ids": []}, "tip"),
            ({"anchor_id": "edge_001"}, "edge_001"),
        ):
            with self.subTest(**{key: str(value) for key, value in kwargs.items()}):
                refused = self.refused(self.park, **kwargs)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)

    def test_every_reason_code_in_the_table_is_accepted(self) -> None:
        for code in ("insufficient_evidence", "low_decision_value", "contradicted", "duplicate", "out_of_scope"):
            with self.subTest(code=code):
                self.assertEqual(self.park(reason_code=code)["state"]["lines"][-1]["reason_code"], code)

    def test_a_node_can_be_in_more_than_one_line(self) -> None:
        self.park()
        state = self.park(["node_003", "node_005"], tip_ids=("node_005",))["state"]
        self.assertEqual([line["id"] for line in state["lines"]], ["line_001", "line_002"])


class ReopenALine(Lines):
    def test_a_reopen_keeps_the_episode_and_frees_the_nodes(self) -> None:
        self.park()
        state = self.reopen()["state"]
        line = state["lines"][0]
        self.assertEqual(line["status"], "reopened")
        self.assertEqual(line["reopening"], {"reason": "A second supplier now quotes at volume.", "actor": OWNER})
        self.assertEqual(line["node_ids"], ["node_002", "node_003"], "the episode stays in the record")
        self.assertEqual(self.grounding("node_005")["parked"], [])
        self.assertEqual(self.grounding("node_005")["band"], "solid")
        self.assertEqual(self.co.history(self.sid)[-1]["type"], "line.reopened")
        self.assertEqual(coordinator(self.store).state(self.sid), state, "a restarted coordinator folds the same")

    def test_a_node_stays_parked_while_another_parked_line_holds_it(self) -> None:
        self.park()
        self.park(["node_003", "node_005"], tip_ids=("node_005",))
        self.reopen("line_001")
        self.assertEqual(self.grounding("node_005")["parked"], ["node_003", "node_005"])

    def test_a_second_reopen_an_unknown_line_or_an_empty_reason_is_refused(self) -> None:
        self.park()
        self.reopen()
        for kwargs, naming in (
            ({"line_id": "line_001"}, "already reopened"),
            ({"line_id": "line_099"}, "no parked line"),
            ({"line_id": "line_001", "reason": ""}, "reason"),
        ):
            with self.subTest(**kwargs):
                refused = self.refused(self.reopen, **kwargs)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)


class TheGuiParksAndReopensAsThePerson(Lines):
    def test_the_gui_routes_reach_the_commands_as_the_operator(self) -> None:
        import re

        from frameshift.gui.server import ROUTES, ManualApp

        routed = {name: re.compile(pattern) for method, pattern, name in ROUTES}
        self.assertTrue(routed["line_proposal"].match(f"/api/sessions/{self.sid}/lines/proposal"))
        self.assertTrue(routed["park_line"].match(f"/api/sessions/{self.sid}/lines"))
        self.assertTrue(routed["reopen_line"].match(f"/api/sessions/{self.sid}/lines/line_001/reopen"))
        app = ManualApp(self.co, token="test-token-0123456789", vocabulary={}, record=None)
        proposed = app.line_proposal({"anchor_id": "node_001", "tip_ids": ["node_003", "node_004"]}, self.sid)
        self.assertEqual(proposed, {"node_ids": ["node_002", "node_003", "node_004"]})
        app.park_line({
            "anchor_id": "node_001", "tip_ids": ["node_003", "node_004"], "node_ids": proposed["node_ids"],
            "reason_code": "low_decision_value", "reason": REASON, "expected_revision": self.revision(),
        }, self.sid)
        view = app.reopen_line({"reason": "It matters after all.", "expected_revision": self.revision()}, self.sid, "line_001")
        self.assertEqual(view["state"]["lines"][0]["status"], "reopened")
        self.assertEqual(view["state"]["lines"][0]["actor"], OWNER)


class OnlyThePersonParks(unittest.TestCase):
    """ADR-0032: no reasoner-facing boundary names the park or reopen command."""

    def test_no_reasoner_facing_boundary_names_park_or_reopen(self) -> None:
        for path in sorted((ROOT / "frameshift" / "mcp").rglob("*.py")) + sorted((ROOT / "adapters").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for command in ("park_line", "reopen_line"):
                with self.subTest(path=path.relative_to(ROOT).as_posix(), command=command):
                    self.assertNotIn(command, source)


if __name__ == "__main__":
    unittest.main()
