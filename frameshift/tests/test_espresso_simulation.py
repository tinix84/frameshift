#!/usr/bin/env python3
"""The espresso corpus case runs through the real application (scripts/simulate_espresso.py).

Gates are approved by the test helper, as in the rest of this suite: no person
approves anything here, and the store is a temporary directory. The script
itself never prepares or answers a gate, which these tests check.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import simulate_espresso as simulation  # noqa: E402
from frameshift.tests.test_sessions import approve, coordinator  # noqa: E402
from frameshift.validation import session_violations  # noqa: E402

GATE_METHODS = ("prepare_gate", "confirm", "cancel")


class GateSpy:
    """Wraps a coordinator and records any gate call the script makes."""

    def __init__(self, co) -> None:
        self._co = co
        self.gate_calls: list[str] = []

    def __getattr__(self, name):
        if name in GATE_METHODS:
            self.gate_calls.append(name)
        return getattr(self._co, name)


def seal(co, sim, gate: str, target_reference_id: str) -> None:
    approve(co, co.prepare_gate(sim.session_id, gate=gate, target_id=sim.ids[target_reference_id]))


class AFullRun(unittest.TestCase):
    """One run of every stage, shared by the assertions below (it takes a few seconds)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        store = cls._store = Path(cls._dir.name)
        cls.co = coordinator(store)
        cls.spy = GateSpy(cls.co)
        cls.sim = simulation.Simulation(store)
        cls.ref = simulation.reference()
        simulation.stage_intake(cls.spy, cls.sim, cls.ref)
        seal(cls.co, cls.sim, "intake_correction", cls.ref["statements"][0]["id"])
        simulation.stage_framing(cls.spy, cls.sim, cls.ref)
        seal(cls.co, cls.sim, "frame_selection", cls.ref["active_frame_id"])
        cls.causal_lines = simulation.stage_causal(cls.spy, cls.sim, cls.ref)
        cls.state = cls.co.state(cls.sim.session_id)
        cls.report = simulation.compare(cls.state, cls.ref, cls.sim)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._dir.cleanup()

    def test_every_stage_lands_and_the_session_stays_valid(self) -> None:
        self.assertFalse([line for line in self.causal_lines if line.startswith("Refused")], self.causal_lines)
        self.assertEqual(self.state["phase"], "causal")
        self.assertEqual(session_violations(self.state), [])
        counts = [len(self.state[k]) for k in ("statements", "ladder", "frames", "symptom_specifications")]
        counts += [len(self.state["graph"][k]) for k in ("nodes", "edges")]
        self.assertEqual(counts, [12, 4, 4, 2, 43, 52])

    def test_a_finished_causal_stage_adds_nothing_when_run_again(self) -> None:
        before = len(self.co.history(self.sim.session_id))
        lines = simulation.stage_causal(self.co, simulation.Simulation(self._store), self.ref)
        self.assertEqual(len(self.co.history(self.sim.session_id)), before, lines)
        self.assertIn("Symptom specifications: 2 kept.", lines)

    def test_the_script_never_touches_a_gate(self) -> None:
        self.assertEqual(self.spy.gate_calls, [])
        approvals = [a["target_id"] for a in self.state["approvals"]]
        # Exactly the two the test helper sealed, nothing the script added.
        self.assertEqual(len(approvals), 2)

    def test_no_reasoner_offer_carries_a_decided_status(self) -> None:
        statuses = {node["status"] for node in self.state["graph"]["nodes"]}
        statuses |= {edge["status"] for edge in self.state["graph"]["edges"]}
        self.assertLessEqual(statuses, set(simulation.REASONER_STATUSES))

    def test_only_the_observed_nodes_differ_in_provenance_and_only_by_kind(self) -> None:
        """#257: every declared kind is kept; observed is the person's and comes out inferred here."""
        observed = {node["id"] for node in self.ref["graph"]["nodes"] if node["provenance"]["kind"] == "observed"}
        differing = {
            row["id"] for row in self.report["sections"]["nodes"]
            if any(difference.startswith("provenance") for difference in row["differences"])
        }
        self.assertEqual(differing, observed)
        held = {node["id"]: node for node in self.state["graph"]["nodes"]}
        back = {mine: theirs for theirs, mine in self.sim.ids.items()}
        for node in self.ref["graph"]["nodes"]:
            mine = dict(held[self.sim.ids[node["id"]]]["provenance"])
            mine["source_ids"] = [back.get(source, source) for source in mine["source_ids"]]
            if node["id"] in observed:
                self.assertEqual(mine["kind"], "inferred", node["id"])
                mine["kind"] = "observed"
            self.assertEqual(mine, node["provenance"], node["id"])

    def test_the_comparison_is_pinned(self) -> None:
        summary = {}
        for name, rows in self.report["sections"].items():
            identical = sum(1 for row in rows if not row["differences"])
            missing = sum(1 for row in rows if row["differences"] == ["missing"])
            summary[name] = (len(rows), identical, missing, len(self.report["extra"][name]))
        self.assertEqual(
            summary,
            {
                "statements": (12, 0, 0, 0),
                "ladder": (4, 4, 0, 0),
                "frames": (4, 3, 0, 0),
                "nodes": (43, 32, 0, 0),
                "edges": (52, 0, 0, 0),
                # Both deviations, the three-row one included (ADR-0027).
                "specifications": (2, 2, 0, 0),
            },
        )
        fields: dict[tuple[str, str], int] = {}
        for name, rows in self.report["sections"].items():
            for row in rows:
                for difference in row["differences"]:
                    key = (name, difference.split(":", 1)[0])
                    fields[key] = fields.get(key, 0) + 1
        self.assertEqual(
            fields,
            {
                # The script is a reasoner (ADR-0028): nine observed statements come out assumed, and the
                # request differs in its intake id and note. The two inferred ones reproduce.
                ("statements", "provenance"): 10,
                ("statements", "status"): 12,
                ("frames", "status"): 1,
                # Observed in the reference, offered as inferred: the script's statements are not the
                # person's, so they cannot earn observed (ADR-0028). Every other kind is kept (ADR-0026).
                ("nodes", "provenance"): 10,
                ("nodes", "status"): 2,  # rejected and superseded: the person's to decide (#254)
                ("edges", "extensions"): 52,
                ("edges", "provenance"): 52,
                ("edges", "status"): 9,
            },
        )
        # The specification is session state now; citation records stay checkpoint artifacts (ADR-0027).
        self.assertEqual(
            self.report["session"]["extensions"]["reference"],
            ["citations", "corpus", "symptom_specification.note", "symptom_specification.status", "views"],
        )
        self.assertEqual(self.report["session"]["extensions"]["application"], [])


class StagesResumeAndRunInOrder(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = Path(self._dir.name)
        self.co = coordinator(self.store)
        self.sim = simulation.Simulation(self.store)
        self.ref = simulation.reference()

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_a_stage_refuses_to_run_before_its_gate_is_sealed(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        with self.assertRaises(SystemExit) as stopped:
            simulation.stage_framing(self.co, self.sim, self.ref)
        self.assertIn("seal the previous gate", str(stopped.exception))
        self.assertEqual(self.co.state(self.sim.session_id)["phase"], "intake")

    def to_framing(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        seal(self.co, self.sim, "intake_correction", self.ref["statements"][0]["id"])

    def test_a_refused_stage_resumes_without_repeating_or_locking_the_store(self) -> None:
        """Review of #252: a revision conflict with the GUI open must not strand the store."""
        from frameshift.orchestration.api import CommandRefused

        self.to_framing()

        class ConflictOnSecondFrame:
            def __init__(self, co) -> None:
                self._co, self.frames = co, 0

            def __getattr__(self, name):
                return getattr(self._co, name)

            def propose_frame(self, *args, **kwargs):
                self.frames += 1
                if self.frames == 2:
                    raise CommandRefused("revision_conflict", "the GUI committed first")
                return self._co.propose_frame(*args, **kwargs)

        with self.assertRaises(CommandRefused):
            simulation.stage_framing(ConflictOnSecondFrame(self.co), self.sim, self.ref)
        lines = simulation.stage_framing(self.co, simulation.Simulation(self.store), self.ref)
        self.assertIn("5 kept", lines[0])
        state = self.co.state(self.sim.session_id)
        self.assertEqual((len(state["ladder"]), len(state["frames"])), (4, 4))
        before = len(self.co.history(self.sim.session_id))
        simulation.stage_framing(self.co, simulation.Simulation(self.store), self.ref)
        self.assertEqual(len(self.co.history(self.sim.session_id)), before, "a finished stage adds nothing")

    def test_a_look_alike_the_person_added_is_not_adopted(self) -> None:
        """Re-check of #252: same question, different content, is the person's frame, not the script's."""
        self.to_framing()
        frame = {k: v for k, v in self.ref["frames"][0].items() if k not in {"id", "status", "digest"}}
        frame["outcome"] = "The person's own outcome."
        self.co.propose_frame(self.sim.session_id, frame=frame, expected_revision=self.co.state(self.sim.session_id)["revision"])
        lines = simulation.stage_framing(self.co, self.sim, self.ref)
        self.assertNotIn("adopted", lines[0])
        report = simulation.compare(self.co.state(self.sim.session_id), self.ref, self.sim)
        self.assertEqual(report["extra"]["frames"], ["frame_001"])

    def test_an_item_committed_before_the_map_was_saved_is_adopted_not_repeated(self) -> None:
        self.to_framing()
        rung = dict(self.ref["ladder"][0])
        rung.pop("id")
        rung["provenance"] = dict(rung["provenance"], source_ids=self.sim.mapped(rung["provenance"]["source_ids"]))
        self.co.record_rung(self.sim.session_id, rung=rung, expected_revision=self.co.state(self.sim.session_id)["revision"])
        lines = simulation.stage_framing(self.co, self.sim, self.ref)
        self.assertIn("1 adopted", lines[0])
        self.assertEqual(len(self.co.state(self.sim.session_id)["ladder"]), 4)

    def test_the_comparison_counts_what_the_reference_does_not_hold(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        sid = self.sim.session_id
        self.co.add_statement(sid, text="An extra line.", primary_role="observation", expected_revision=self.co.state(sid)["revision"])
        report = simulation.compare(self.co.state(sid), self.ref, self.sim)
        self.assertEqual(report["extra"]["statements"], ["stmt_013"])
        self.assertIn("extra statements", simulation.render(report))


if __name__ == "__main__":
    unittest.main()
