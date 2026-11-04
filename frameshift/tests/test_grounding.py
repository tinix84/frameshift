#!/usr/bin/env python3
"""Tests for the grounding derivation (#274, ADR-0031).

Each test builds a small graph and reads what the derivation says about it.
Grounding is derived on read: it is never recorded, never covered by the
state digest, and it never refuses a command.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration.grounding import derive  # noqa: E402
from frameshift.persistence.canonical import digest  # noqa: E402
from frameshift.tests.test_sessions import InCausal  # noqa: E402

BATTERY = ROOT / "outputs" / "battery-chat-walkthrough-20261018" / "argument-graph.json"


def node(node_id: str, kind: str, *, status: str = "proposed", type_: str = "factor") -> dict:
    return {
        "id": node_id,
        "type": type_,
        "label": node_id,
        "status": status,
        "confidence": "unknown",
        "provenance": {"kind": kind, "source_ids": []},
    }


def edge(edge_id: str, source: str, target: str, type_: str = "supports", *, status: str = "proposed") -> dict:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": type_,
        "status": status,
        "confidence": "unknown",
        "provenance": {"kind": "assumed", "source_ids": [source, target]},
    }


def state(nodes: list[dict], edges: list[dict] = ()) -> dict:
    return {"graph": {"schema_version": "1.0.0", "nodes": list(nodes), "edges": list(edges)}}


def profile(graph_state: dict, node_id: str) -> dict:
    return derive(graph_state)["nodes"][node_id]


class TheGroundSet(unittest.TestCase):
    """ADR-0031: the distinct bases a node rests on."""

    def test_two_paths_to_one_fact_count_it_once(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_a", "inferred"), node("node_b", "inferred"), node("node_top", "inferred")],
            [
                edge("edge_1", "node_fact", "node_a"),
                edge("edge_2", "node_fact", "node_b"),
                edge("edge_3", "node_a", "node_top"),
                edge("edge_4", "node_b", "node_top"),
            ],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["bases"]["fact"], ["node_fact"])
        self.assertEqual(top["band"], "solid")

    def test_a_cycle_of_inferences_ends_and_is_weak(self) -> None:
        graph = state(
            [node("node_a", "inferred"), node("node_b", "inferred"), node("node_c", "inferred")],
            [edge("edge_1", "node_a", "node_b"), edge("edge_2", "node_b", "node_c"), edge("edge_3", "node_c", "node_a")],
        )
        for node_id in ("node_a", "node_b", "node_c"):
            with self.subTest(node=node_id):
                found = profile(graph, node_id)
                self.assertEqual(found["bases"]["fact"], [])
                self.assertEqual(found["band"], "weak")

    def test_a_rejected_base_makes_every_node_above_it_weak(self) -> None:
        graph = state(
            [
                node("node_gone", "observed", status="rejected"),
                node("node_fact", "sourced"),
                node("node_mid", "inferred"),
                node("node_top", "inferred"),
            ],
            [
                edge("edge_1", "node_gone", "node_mid"),
                edge("edge_2", "node_fact", "node_mid"),
                edge("edge_3", "node_mid", "node_top"),
            ],
        )
        for node_id in ("node_mid", "node_top"):
            with self.subTest(node=node_id):
                found = profile(graph, node_id)
                self.assertEqual(found["broken"], ["node_gone"])
                self.assertEqual(found["weakest"], "node_gone")
                self.assertEqual(found["band"], "weak")

    def test_superseded_and_archived_bases_are_broken_too(self) -> None:
        for status in ("superseded", "archived"):
            with self.subTest(status=status):
                graph = state(
                    [node("node_base", "observed", status=status), node("node_top", "inferred")],
                    [edge("edge_1", "node_base", "node_top")],
                )
                self.assertEqual(profile(graph, "node_top")["broken"], ["node_base"])

    def test_the_walk_does_not_follow_an_edge_that_is_not_live(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_top", "inferred")],
            [edge("edge_1", "node_fact", "node_top", status="rejected")],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["bases"]["inference"], ["node_top"], "an unsupported inference is its own base")
        self.assertEqual(top["band"], "weak")

    def test_enables_and_requires_add_no_base(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_top", "inferred")],
            [edge("edge_1", "node_fact", "node_top", "enables"), edge("edge_2", "node_fact", "node_top", "requires")],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["bases"]["fact"], [])
        self.assertEqual(top["bases"]["inference"], ["node_top"])

    def test_tests_adds_a_base_only_from_evidence(self) -> None:
        graph = state(
            [
                node("node_evidence", "sourced", type_="evidence"),
                node("node_factor", "sourced"),
                node("node_hypothesis", "inferred", type_="hypothesis"),
            ],
            [
                edge("edge_1", "node_evidence", "node_hypothesis", "tests"),
                edge("edge_2", "node_factor", "node_hypothesis", "tests"),
            ],
        )
        self.assertEqual(profile(graph, "node_hypothesis")["bases"]["fact"], ["node_evidence"])

    def test_derived_from_makes_the_source_rest_on_the_target(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_derived", "inferred")],
            [edge("edge_1", "node_derived", "node_fact", "derived_from")],
        )
        self.assertEqual(profile(graph, "node_derived")["bases"]["fact"], ["node_fact"])
        self.assertEqual(profile(graph, "node_fact")["bases"]["fact"], ["node_fact"])

    def test_causes_and_contributes_to_carry_support(self) -> None:
        for type_ in ("causes", "contributes_to", "supports"):
            with self.subTest(type=type_):
                graph = state(
                    [node("node_fact", "observed"), node("node_top", "inferred")],
                    [edge("edge_1", "node_fact", "node_top", type_)],
                )
                self.assertEqual(profile(graph, "node_top")["bases"]["fact"], ["node_fact"])

    def test_the_walk_stops_at_every_node_that_is_not_an_inference(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_opinion", "assumed"), node("node_top", "inferred")],
            [edge("edge_1", "node_fact", "node_opinion"), edge("edge_2", "node_opinion", "node_top")],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["bases"], {"fact": [], "inference": [], "opinion": ["node_opinion"], "gap": []})
        self.assertEqual(top["weakest"], "node_opinion")


class TheProfileAndTheBand(unittest.TestCase):
    """ADR-0031: the grounding profile and the grounding band."""

    def test_each_kind_maps_to_one_class(self) -> None:
        graph = state([node(f"node_{kind}", kind) for kind in ("observed", "sourced", "inferred", "assumed", "unknown")])
        found = derive(graph)["nodes"]
        self.assertEqual(found["node_observed"]["bases"]["fact"], ["node_observed"])
        self.assertEqual(found["node_sourced"]["bases"]["fact"], ["node_sourced"])
        self.assertEqual(found["node_inferred"]["bases"]["inference"], ["node_inferred"])
        self.assertEqual(found["node_assumed"]["bases"]["opinion"], ["node_assumed"])
        self.assertEqual(found["node_unknown"]["bases"]["gap"], ["node_unknown"])

    def test_the_weakest_base_comes_gap_opinion_inference_fact_with_ties_by_id(self) -> None:
        graph = state(
            [
                node("node_fact", "observed"),
                node("node_opinion_b", "assumed"),
                node("node_opinion_a", "assumed"),
                node("node_top", "inferred"),
            ],
            [
                edge("edge_1", "node_fact", "node_top"),
                edge("edge_2", "node_opinion_b", "node_top"),
                edge("edge_3", "node_opinion_a", "node_top"),
            ],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["weakest"], "node_opinion_a")
        self.assertEqual(top["band"], "mixed")

    def test_undecided_bases_are_named(self) -> None:
        graph = state(
            [node("node_draft", "observed", status="draft"), node("node_done", "observed", status="approved"), node("node_top", "inferred")],
            [edge("edge_1", "node_draft", "node_top"), edge("edge_2", "node_done", "node_top")],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["undecided"], ["node_draft"])
        self.assertEqual(top["band"], "solid", "an undecided base informs; it does not lower the band")

    def test_a_contradicts_edge_is_an_open_challenge_on_its_target(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_counter", "assumed")],
            [edge("edge_1", "node_counter", "node_fact", "contradicts")],
        )
        fact = profile(graph, "node_fact")
        self.assertEqual(fact["challenges"]["open"], ["edge_1"])
        self.assertEqual(fact["band"], "weak")

    def test_a_contradicts_edge_that_is_not_live_is_no_challenge(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_counter", "assumed")],
            [edge("edge_1", "node_counter", "node_fact", "contradicts", status="rejected")],
        )
        self.assertEqual(profile(graph, "node_fact")["challenges"]["open"], [])
        self.assertEqual(profile(graph, "node_fact")["band"], "solid")

    def test_an_open_challenge_the_walk_crosses_shows_upstream(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_mid", "inferred"), node("node_top", "inferred"), node("node_counter", "assumed")],
            [
                edge("edge_1", "node_fact", "node_mid"),
                edge("edge_2", "node_mid", "node_top"),
                edge("edge_3", "node_counter", "node_mid", "contradicts"),
            ],
        )
        top = profile(graph, "node_top")
        self.assertEqual(top["upstream_open"], ["edge_3"])
        self.assertEqual(top["challenges"]["open"], [])
        self.assertEqual(top["band"], "mixed", "facts only, with a doubt upstream")
        self.assertEqual(profile(graph, "node_mid")["band"], "weak")

    def test_a_node_with_no_fact_base_is_weak(self) -> None:
        graph = state(
            [node("node_opinion", "assumed"), node("node_top", "inferred")],
            [edge("edge_1", "node_opinion", "node_top")],
        )
        self.assertEqual(profile(graph, "node_top")["band"], "weak")


class SolidGround(unittest.TestCase):
    """ADR-0031: a solid node that no other solid node rests on."""

    def test_solid_ground_is_the_top_of_the_solid_region(self) -> None:
        graph = state(
            [
                node("node_fact", "observed"),
                node("node_mid", "inferred"),
                node("node_opinion", "assumed"),
                node("node_top", "inferred"),
            ],
            [
                edge("edge_1", "node_fact", "node_mid"),
                edge("edge_2", "node_mid", "node_top"),
                edge("edge_3", "node_opinion", "node_top"),
            ],
        )
        found = derive(graph)
        self.assertEqual(found["nodes"]["node_top"]["band"], "mixed")
        self.assertEqual(found["solid_ground"], ["node_mid"])


class GroundingIsDerivedOnRead(unittest.TestCase):
    """ADR-0031: no event records it and the state digest never covers it."""

    def test_deriving_leaves_the_state_and_its_digest_unchanged(self) -> None:
        graph = state(
            [node("node_fact", "observed"), node("node_top", "inferred")],
            [edge("edge_1", "node_fact", "node_top")],
        )
        before = copy.deepcopy(graph)
        recorded = digest(graph)
        derive(graph)
        self.assertEqual(graph, before)
        self.assertEqual(digest(graph), recorded)



class TheSessionViewDerivesGrounding(InCausal):
    """ADR-0031: the view carries grounding under `derived`, as it carries `frame_set`."""

    def test_the_view_derives_grounding_and_writes_nothing(self) -> None:
        self.co.add_node(self.sid, node={"type": "hypothesis", "label": "Cell price dominates.", "source_ids": ["frame_001"]}, expected_revision=self.revision())
        recorded, length = digest(self.co.state(self.sid)), len(self.co.history(self.sid))
        view = self.co.view(self.sid)
        self.assertEqual(view["derived"]["grounding"]["nodes"]["node_001"]["band"], "weak")
        self.assertNotIn("grounding", view["state"])
        self.assertEqual(digest(self.co.state(self.sid)), recorded)
        self.assertEqual(len(self.co.history(self.sid)), length)


class TheBatteryWalkthrough(unittest.TestCase):
    """ADR-0031 Validation: the battery walkthrough graph bands each of its 36 nodes."""

    def test_every_node_gets_a_band(self) -> None:
        graph = json.loads(BATTERY.read_text(encoding="utf-8"))
        found = derive({"graph": graph})
        self.assertEqual(len(graph["nodes"]), 36)
        self.assertEqual(set(found["nodes"]), {item["id"] for item in graph["nodes"]})
        for node_id, item in found["nodes"].items():
            with self.subTest(node=node_id):
                self.assertIn(item["band"], {"solid", "mixed", "weak"})


if __name__ == "__main__":
    unittest.main()
