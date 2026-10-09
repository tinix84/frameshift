#!/usr/bin/env python3
"""The espresso corpus case runs through the real application (scripts/simulate_espresso.py).

Gates are approved by the test helper, as in the rest of this suite: no person
approves anything here, and the store is a temporary directory. The script
itself never approves a gate.
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


class EspressoRunsThroughTheApplication(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = Path(self._dir.name)
        self.co = coordinator(self.store)
        self.sim = simulation.Simulation(self.store)
        self.ref = simulation.reference()

    def tearDown(self) -> None:
        self._dir.cleanup()

    def seal(self, gate: str, target_reference_id: str) -> None:
        target = self.sim.ids[target_reference_id]
        approve(self.co, self.co.prepare_gate(self.sim.session_id, gate=gate, target_id=target))

    def run_all(self) -> dict:
        simulation.stage_intake(self.co, self.sim, self.ref)
        self.seal("intake_correction", self.ref["statements"][0]["id"])
        simulation.stage_framing(self.co, self.sim, self.ref)
        self.seal("frame_selection", self.ref["active_frame_id"])
        lines = simulation.stage_causal(self.co, self.sim, self.ref)
        self.assertFalse([line for line in lines if line.startswith("Refused")], lines)
        return self.co.state(self.sim.session_id)

    def test_every_stage_lands_and_the_session_stays_valid(self) -> None:
        state = self.run_all()
        self.assertEqual(state["phase"], "causal")
        self.assertEqual(session_violations(state), [])
        self.assertEqual(len(state["statements"]), 12)
        self.assertEqual(len(state["ladder"]), 4)
        self.assertEqual(len(state["frames"]), 4)
        self.assertEqual(len(state["graph"]["nodes"]), 43)
        self.assertEqual(len(state["graph"]["edges"]), 52)

    def test_a_stage_refuses_to_run_before_its_gate_is_sealed(self) -> None:
        simulation.stage_intake(self.co, self.sim, self.ref)
        with self.assertRaises(SystemExit) as stopped:
            simulation.stage_framing(self.co, self.sim, self.ref)
        self.assertIn("seal the previous gate", str(stopped.exception))
        self.assertEqual(self.co.state(self.sim.session_id)["phase"], "intake")

    def test_the_comparison_names_what_the_application_cannot_represent(self) -> None:
        state = self.run_all()
        report = simulation.compare(state, self.ref, self.sim)
        missing = {name: [r for r in rows if r["differences"] == ["missing"]] for name, rows in report["sections"].items()}
        self.assertEqual({name: rows for name, rows in missing.items() if rows}, {})
        frames = {row["id"]: row["differences"] for row in report["sections"]["frames"]}
        # No command rejects a frame yet: the supply frame stays proposed.
        self.assertTrue(any(d.startswith("status:") for d in frames["frame_espresso_supply"]))
        statements = {row["id"]: row["differences"] for row in report["sections"]["statements"]}
        # No command supersedes a statement yet.
        self.assertTrue(any(d.startswith("status:") for d in statements["stmt_espresso_006"]))
        self.assertIn("symptom_specification", report["session"]["extensions"]["reference"])
        self.assertNotIn("symptom_specification", report["session"]["extensions"]["application"])


if __name__ == "__main__":
    unittest.main()
