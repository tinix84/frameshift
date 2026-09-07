from __future__ import annotations

import copy
import unittest

from evals import run


CASES = {
    "corpus-tunnel-lights": "tunnel-lights",
    "corpus-bracket-weight-mandate": "bracket-weight-mandate",
}


class NegativeExemplarTests(unittest.TestCase):
    def _case_and_result(self, directory: str) -> tuple[dict, dict]:
        case = run.load(f"corpus/{directory}/{directory}.case.json")
        result = run.load("reference.result.json", run.CORPUS / directory)
        return case, result

    def test_both_negative_exemplars_pass_at_the_arriving_level(self) -> None:
        for case_id, directory in CASES.items():
            with self.subTest(case=case_id):
                case, _ = self._case_and_result(directory)
                self.assertEqual(run.evaluate(case, lambda name: run.load(name, run.CORPUS / directory)), [])

    def test_each_reference_frame_above_ceiling_is_caught(self) -> None:
        for case_id, directory in CASES.items():
            with self.subTest(case=case_id):
                case, result = self._case_and_result(directory)
                mutated = copy.deepcopy(result)
                frame = next(item for item in mutated["proposals"] if item["kind"] == "problem_frame")
                frame["value"]["abstraction_level"] = "product"
                errors = run.evaluate(case, lambda name, result=mutated, directory=directory: result if name == "reference.result.json" else run.load(name, run.CORPUS / directory))
                self.assertTrue(any("exceeds maximum" in error for error in errors), errors)

    def test_each_reference_ladder_above_ceiling_is_caught(self) -> None:
        for case_id, directory in CASES.items():
            with self.subTest(case=case_id):
                case, result = self._case_and_result(directory)
                mutated = copy.deepcopy(result)
                ladder = next(item for item in mutated["proposals"] if item["kind"] == "abstraction_ladder")
                ladder["value"]["levels"] = ["component", "product"]
                errors = run.evaluate(case, lambda name, result=mutated, directory=directory: result if name == "reference.result.json" else run.load(name, run.CORPUS / directory))
                self.assertTrue(any("exceeds maximum" in error for error in errors), errors)

    def test_boundary_case_records_higher_frame_as_out_of_scope(self) -> None:
        _, result = self._case_and_result("bracket-weight-mandate")
        self.assertTrue(any("out of scope" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
