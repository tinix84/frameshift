#!/usr/bin/env python3
"""Tests for challenges on graph nodes and edges (#275, ADR-0031).

Anyone may raise a challenge, a reasoner-facing boundary included: doubt
decides nothing. Only the person answers or concedes one, and an answer cites
sources that resolve in the session.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration.api import CommandRefused  # noqa: E402
from frameshift.tests.test_sessions import OWNER, InCausal, coordinator  # noqa: E402
from frameshift.validation import session_violations  # noqa: E402

REASONER = {"id": "svc_reasoner", "kind": "service"}


class Challenges(InCausal):
    """A causal graph: a fact, an opinion, and two inferences resting on the fact."""

    def setUp(self) -> None:
        super().setUp()
        self.node({"type": "evidence", "label": "Quote at volume.", "provenance": {"kind": "sourced", "source_ids": ["art_quote"]}})
        self.node({"type": "assumption", "label": "Volume holds next year."})
        self.node({"type": "hypothesis", "label": "Cell price dominates.", "provenance": {"kind": "inferred", "source_ids": ["node_001"]}})
        self.node({"type": "hypothesis", "label": "Sourcing is the lever.", "provenance": {"kind": "inferred", "source_ids": ["node_003"]}})
        self.edge("node_001", "node_003")
        self.edge("node_003", "node_004")

    def node(self, node: dict) -> None:
        self.co.add_node(self.sid, node=node, expected_revision=self.revision())

    def edge(self, source: str, target: str) -> None:
        self.co.add_edge(self.sid, edge={"source": source, "target": target, "type": "supports"}, expected_revision=self.revision())

    def raise_(self, target_id: str, objection: str = "The quote is a single supplier.", actor: dict = REASONER) -> dict:
        return self.co.raise_challenge(self.sid, target_id=target_id, objection=objection, actor=actor, expected_revision=self.revision())

    def answer(self, challenge_id: str, source_ids, note: str | None = None) -> dict:
        return self.co.answer_challenge(self.sid, challenge_id=challenge_id, source_ids=source_ids, note=note, expected_revision=self.revision())

    def concede(self, challenge_id: str) -> dict:
        return self.co.concede_challenge(self.sid, challenge_id=challenge_id, expected_revision=self.revision())

    def grounding(self, node_id: str) -> dict:
        return self.co.view(self.sid)["derived"]["grounding"]["nodes"][node_id]

    def refused(self, command, *args, **kwargs) -> CommandRefused:
        before = len(self.co.history(self.sid))
        with self.assertRaises(CommandRefused) as refused:
            command(*args, **kwargs)
        self.assertEqual(len(self.co.history(self.sid)), before, "a refused command writes nothing")
        return refused.exception


class RaiseAChallenge(Challenges):
    def test_a_reasoner_raises_a_challenge_on_a_node(self) -> None:
        state = self.raise_("node_003")["state"]
        self.assertEqual(
            state["challenges"],
            [{"id": "chal_001", "target_id": "node_003", "objection": "The quote is a single supplier.", "actor": REASONER, "status": "open"}],
        )
        event = self.co.history(self.sid)[-1]
        self.assertEqual((event["type"], event["payload"]["actor"]), ("challenge.raised", REASONER))
        self.assertEqual(self.grounding("node_003")["challenges"]["open"], ["chal_001"])
        self.assertEqual(self.grounding("node_003")["band"], "weak")
        self.assertEqual(session_violations(state), [])

    def test_raising_a_challenge_changes_no_status(self) -> None:
        before = self.co.state(self.sid)["graph"]
        self.assertEqual(self.raise_("node_003")["state"]["graph"], before)

    def test_an_open_challenge_on_a_support_edge_shows_upstream_above_it(self) -> None:
        self.raise_("edge_001")
        for node_id in ("node_003", "node_004"):
            with self.subTest(node=node_id):
                found = self.grounding(node_id)
                self.assertEqual(found["upstream_open"], ["chal_001"])
                self.assertEqual(found["challenges"]["open"], [])
                self.assertEqual(found["band"], "mixed")

    def test_an_unknown_target_or_an_empty_objection_is_refused(self) -> None:
        for target_id, objection, naming in (
            ("node_099", "Doubtful.", "no graph node or edge"),
            ("stmt_001", "Doubtful.", "no graph node or edge"),
            ("node_003", "   ", "objection"),
            ("node_003", None, "objection"),
        ):
            with self.subTest(target=target_id, objection=objection):
                refused = self.refused(self.raise_, target_id, objection)
                self.assertEqual(refused.code, "invariant_violation")
                self.assertIn(naming, refused.detail)

    def test_an_actor_that_is_not_an_actor_is_refused(self) -> None:
        refused = self.refused(self.raise_, "node_003", actor={"id": "svc_reasoner", "kind": "model"})
        self.assertEqual(refused.code, "schema_invalid")


class AnswerAChallenge(Challenges):
    def test_an_answer_citing_an_assumption_is_answered_by_opinion(self) -> None:
        self.raise_("node_003")
        state = self.answer("chal_001", ["node_002"])["state"]
        challenge = state["challenges"][0]
        self.assertEqual(challenge["status"], "answered")
        self.assertEqual(challenge["answer"], {"source_ids": ["node_002"], "actor": OWNER})
        self.assertEqual(self.grounding("node_003")["challenges"]["answered_by_opinion"], ["chal_001"])

    def test_an_answer_citing_only_facts_is_answered_by_fact(self) -> None:
        self.raise_("node_003")
        self.answer("chal_001", ["node_001", "art_second_quote"], note="Two suppliers quote the same price.")
        found = self.grounding("node_003")
        self.assertEqual(found["challenges"]["answered_by_fact"], ["chal_001"])
        self.assertEqual(found["band"], "solid")
        event = self.co.history(self.sid)[-1]
        self.assertEqual((event["type"], event["payload"]["actor"]), ("challenge.answered", OWNER))

    def test_an_answer_with_a_source_that_does_not_resolve_is_refused(self) -> None:
        self.raise_("node_003")
        for source_ids, code in (
            (["node_099"], "invariant_violation"),
            (["node_001", "node_099"], "invariant_violation"),
            (["zzz_unknown"], "invariant_violation"),
            (["intake_never_minted"], "invariant_violation"),
            ([], "invariant_violation"),
            ("node_001", "schema_invalid"),
        ):
            with self.subTest(source_ids=source_ids):
                self.assertEqual(self.refused(self.answer, "chal_001", source_ids).code, code)
        self.assertEqual(self.co.state(self.sid)["challenges"][0]["status"], "open")

    def test_only_an_open_challenge_is_answered_or_conceded(self) -> None:
        self.raise_("node_003")
        self.answer("chal_001", ["node_001"])
        for command in (lambda: self.answer("chal_001", ["node_001"]), lambda: self.concede("chal_001")):
            refused = self.refused(command)
            self.assertIn("already answered", refused.detail)
        for command in (lambda: self.answer("chal_099", ["node_001"]), lambda: self.concede("chal_099")):
            self.assertIn("no challenge", self.refused(command).detail)


class ConcedeAChallenge(Challenges):
    def test_a_conceded_challenge_makes_the_node_weak_and_changes_no_status(self) -> None:
        self.raise_("node_001")
        graph = self.co.state(self.sid)["graph"]
        state = self.concede("chal_001")["state"]
        self.assertEqual(state["challenges"][0]["status"], "conceded")
        self.assertEqual(state["challenges"][0]["concession"], {"actor": OWNER})
        self.assertEqual(state["graph"], graph)
        found = self.grounding("node_001")
        self.assertEqual((found["challenges"]["conceded"], found["band"]), (["chal_001"], "weak"))
        self.assertEqual(self.co.history(self.sid)[-1]["type"], "challenge.conceded")
        self.assertEqual(coordinator(self.store).state(self.sid), state, "a restarted coordinator folds the same")


class TheGuiSpeaksForThePerson(Challenges):
    """The manual GUI raises, answers and concedes as the operator (ADR-0022, ADR-0031)."""

    def test_the_gui_routes_reach_the_three_commands_as_the_operator(self) -> None:
        import re

        from frameshift.gui.server import ROUTES, ManualApp

        routed = {
            name: re.compile(pattern)
            for method, pattern, name in ROUTES
            if name in {"raise_challenge", "answer_challenge", "concede_challenge"}
        }
        self.assertTrue(routed["raise_challenge"].match(f"/api/sessions/{self.sid}/challenges"))
        self.assertTrue(routed["answer_challenge"].match(f"/api/sessions/{self.sid}/challenges/chal_001/answer"))
        self.assertTrue(routed["concede_challenge"].match(f"/api/sessions/{self.sid}/challenges/chal_002/concede"))
        app = ManualApp(self.co, token="test-token-0123456789", vocabulary={}, record=None)
        app.raise_challenge({"target_id": "node_003", "objection": "One supplier.", "expected_revision": self.revision()}, self.sid)
        app.raise_challenge({"target_id": "node_004", "objection": "Not shown.", "expected_revision": self.revision()}, self.sid)
        app.answer_challenge({"source_ids": ["node_001"], "expected_revision": self.revision()}, self.sid, "chal_001")
        view = app.concede_challenge({"expected_revision": self.revision()}, self.sid, "chal_002")
        challenges = view["state"]["challenges"]
        self.assertEqual([item["actor"] for item in challenges], [OWNER, OWNER])
        self.assertEqual([item["status"] for item in challenges], ["answered", "conceded"])


class OnlyThePersonClosesAChallenge(unittest.TestCase):
    """ADR-0031: no reasoner-facing boundary names the commands that close a challenge."""

    def test_no_reasoner_facing_boundary_names_answer_or_concede(self) -> None:
        for path in sorted((ROOT / "frameshift" / "mcp").rglob("*.py")) + sorted((ROOT / "adapters").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for command in ("answer_challenge", "concede_challenge"):
                with self.subTest(path=path.relative_to(ROOT).as_posix(), command=command):
                    self.assertNotIn(command, source)


if __name__ == "__main__":
    unittest.main()
