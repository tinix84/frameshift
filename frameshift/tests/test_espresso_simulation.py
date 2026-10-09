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
        store = Path(cls._dir.name)
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
        counts = [len(self.state[k]) for k in ("statements", "ladder", "frames")]
        counts += [len(self.state["graph"][k]) for k in ("nodes", "edges")]
        self.assertEqual(counts, [12, 4, 4, 43, 52])

    def test_the_script_never_touches_a_gate(self) -> None:
        self.assertEqual(self.spy.gate_calls, [])
        approvals = [a["target_id"] for a in self.state["approvals"]]
        # Exactly the two the test helper sealed, nothing the script added.
        self.assertEqual(len(approvals), 2)

    def test_no_reasoner_offer_carries_a_decided_status(self) -> None:
        statuses = {node["status"] for node in self.state["graph"]["nodes"]}
        statuses |= {edge["status"] for edge in self.state["graph"]["edges"]}
        self.assertLessEqual(statuses, set(simulation.REASONER_STATUSES))

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
                "nodes": (43, 0, 0, 0),
                "edges": (52, 0, 0, 0),
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
                ("statements", "provenance"): 12,
                ("statements", "status"): 12,
                ("frames", "status"): 1,
                ("nodes", "provenance"): 43,
                ("nodes", "status"): 2,  # rejected and superseded: the person's to decide (#254)
                ("edges", "extensions"): 52,
                ("edges", "provenance"): 52,
                ("edges", "status"): 9,
            },
        )
        self.assertIn("symptom_specification", self.report["session"]["extensions"]["reference"])
        self.assertEqual(self.report["session"]["extensions"]["application"], [])


class StagesRunOnceAndInOrder(unittest.TestCase):
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

    def test_a_stage_that_ran_in_part_is_refused_rather_than_repeated(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        seal(self.co, self.sim, "intake_correction", self.ref["statements"][0]["id"])
        # An interrupted framing stage: one rung landed and was saved before the stop.
        working = [frame for frame in self.ref["frames"] if frame["status"] == "working"]
        partial = dict(self.ref, ladder=self.ref["ladder"][:1], frames=working)
        simulation.stage_framing(self.co, self.sim, partial)
        before = len(self.co.history(self.sim.session_id))
        with self.assertRaises(SystemExit) as stopped:
            simulation.stage_framing(self.co, simulation.Simulation(self.store), self.ref)
        self.assertIn("already ran", str(stopped.exception))
        self.assertEqual(len(self.co.history(self.sim.session_id)), before)

    def test_the_comparison_counts_what_the_reference_does_not_hold(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        sid = self.sim.session_id
        self.co.add_statement(sid, text="An extra line.", primary_role="observation", expected_revision=self.co.state(sid)["revision"])
        report = simulation.compare(self.co.state(sid), self.ref, self.sim)
        self.assertEqual(report["extra"]["statements"], ["stmt_013"])
        self.assertIn("extra statements", simulation.render(report))


if __name__ == "__main__":
    unittest.main()
