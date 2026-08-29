#!/usr/bin/env python3
"""Tests for the harness dispatch seam itself."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from evals.checks import REGISTRY  # noqa: E402


class DispatchTests(unittest.TestCase):
    def test_unknown_check_is_a_named_error(self) -> None:
        errors = run.evaluate({"id": "x", "check": "no_such_check"})
        self.assertEqual(len(errors), 1)
        self.assertIn("unknown check: no_such_check", errors[0])

    def test_missing_check_is_a_named_error(self) -> None:
        errors = run.evaluate({"id": "x"})
        self.assertEqual(len(errors), 1)
        self.assertIn("declares no check", errors[0])

    def test_every_fixture_declares_a_registered_check(self) -> None:
        for path in sorted(run.FIXTURES.glob("*.case.json")):
            case = run.load(str(path.relative_to(run.ROOT)))
            self.assertIn(case.get("check"), REGISTRY, path.name)


if __name__ == "__main__":
    unittest.main()
