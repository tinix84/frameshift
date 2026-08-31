#!/usr/bin/env python3
"""Tests for the phase machine.

The table is not an opinion formed in `phases.py`: the phases mirror the schema
enum and every `(gate, to_phase)` pair appears in the committed approval
fixtures. These tests assert both mirrors still hold, so the table cannot drift
from the contracts it was read out of.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.orchestration import phases  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures"


def fixture_pairs() -> set[tuple[str, str]]:
    """Every accepted `(gate, to_phase)` the approval corpus declares."""
    pairs: set[tuple[str, str]] = set()
    for path in sorted(FIXTURES.glob("approval-*.case.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        for attempt in case.get("attempts", []):
            if attempt.get("expect", {}).get("outcome") == "accepted":
                pairs.add((attempt["gate"], attempt["to_phase"]))
    return pairs


class MirrorTests(unittest.TestCase):
    def test_phases_mirror_the_session_schema(self) -> None:
        schema = json.loads((ROOT / "schemas" / "session.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(phases.PHASES), schema["properties"]["phase"]["enum"])

    def test_every_gate_target_matches_the_approval_corpus(self) -> None:
        pairs = fixture_pairs()
        self.assertTrue(pairs, "the corpus must declare some accepted transitions")
        for gate, to_phase in sorted(pairs):
            with self.subTest(gate=gate):
                self.assertIn(gate, phases.GATES)
                self.assertEqual(phases.GATES[gate].to_phase, to_phase)

    def test_the_corpus_covers_every_gate(self) -> None:
        self.assertEqual({gate for gate, _ in fixture_pairs()}, set(phases.GATES))

    def test_every_from_and_to_phase_is_a_real_phase(self) -> None:
        for gate in phases.GATES.values():
            with self.subTest(gate=gate.name):
                self.assertIn(gate.from_phase, phases.PHASES)
                self.assertIn(gate.to_phase, phases.PHASES)


class ShapeTests(unittest.TestCase):
    def test_six_gates_advance_and_two_do_not(self) -> None:
        advancing = {name for name, gate in phases.GATES.items() if gate.advances}
        self.assertEqual(
            set(phases.GATES) - advancing, {"external_action", "knowledge_promotion"}
        )
        self.assertEqual(len(advancing), 6)

    def test_an_advancing_gate_never_moves_backwards(self) -> None:
        order = list(phases.PHASES)
        for gate in phases.GATES.values():
            if gate.advances:
                with self.subTest(gate=gate.name):
                    self.assertGreater(order.index(gate.to_phase), order.index(gate.from_phase))

    def test_every_phase_but_the_last_has_a_way_out(self) -> None:
        for phase in phases.PHASES[:-1]:
            with self.subTest(phase=phase):
                advancing = [
                    name for name in phases.gates_from(phase) if phases.GATES[name].advances
                ]
                self.assertTrue(advancing, f"{phase} is a dead end")


class AdvanceTests(unittest.TestCase):
    def test_a_legal_transition_is_accepted(self) -> None:
        self.assertEqual(phases.advance("framing", "frame_selection", "causal"), [])

    def test_the_right_gate_in_the_wrong_phase_is_refused(self) -> None:
        """The gap this module exists to close: binding was checked, sequence was not."""
        refusals = phases.advance("intake", "decision_approval", "monitoring")
        self.assertTrue(any("is passed from" in item for item in refusals), refusals)

    def test_a_gate_leading_somewhere_else_is_refused(self) -> None:
        refusals = phases.advance("framing", "frame_selection", "monitoring")
        self.assertTrue(any("leads to" in item for item in refusals), refusals)

    def test_an_unknown_gate_is_refused(self) -> None:
        self.assertTrue(phases.advance("framing", "teleport", "causal"))

    def test_an_unknown_phase_is_refused(self) -> None:
        self.assertTrue(phases.advance("daydreaming", "frame_selection", "causal"))

    def test_a_same_phase_gate_is_legal_without_moving(self) -> None:
        self.assertEqual(phases.advance("causal", "external_action", "causal"), [])
        self.assertEqual(phases.legal_target("external_action", "causal"), "causal")

    def test_every_gate_is_legal_from_exactly_its_own_phase(self) -> None:
        for name, gate in phases.GATES.items():
            for phase in phases.PHASES:
                with self.subTest(gate=name, phase=phase):
                    expected = gate.to_phase if phase == gate.from_phase else None
                    self.assertEqual(phases.legal_target(name, phase), expected)

    def test_the_target_may_be_omitted(self) -> None:
        self.assertEqual(phases.advance("decision", "decision_approval"), [])


if __name__ == "__main__":
    unittest.main()
