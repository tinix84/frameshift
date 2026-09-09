"""The frame-axis contract and explicit checkpoint conversion (#86)."""

import json
import unittest
from pathlib import Path

from frameshift.validation import schema

FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


def reference():
    return json.loads((FIXTURES / "reference.checkpoint.json").read_text(encoding="utf-8"))


class FrameContractTests(unittest.TestCase):
    def test_two_independent_axes_validate_at_the_current_contract(self):
        state = reference()["state"]
        state["schema_version"] = "2.0.0"
        state["frames"][0]["system_boundary"] = "supply_chain"
        self.assertEqual(schema.validate_against(state, "session.schema.json"), [])
        self.assertEqual(state["frames"][0]["abstraction_level"], "product")

    def test_boundary_is_required_and_lateral_values_are_not_ladder_levels(self):
        state = reference()["state"]
        state["schema_version"] = "2.0.0"
        self.assertTrue(any("system_boundary" in e for e in schema.validate_against(state, "session.schema.json")))
        state["frames"][0]["system_boundary"] = "supply_chain"
        state["frames"][0]["abstraction_level"] = "supply_chain"
        self.assertTrue(any("abstraction_level" in e for e in schema.validate_against(state, "session.schema.json")))


if __name__ == "__main__":
    unittest.main()
