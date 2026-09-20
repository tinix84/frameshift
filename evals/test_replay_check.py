#!/usr/bin/env python3
"""Tests that the replay check measures the application reducer (#225).

The fixtures prove the reference history folds to the reference digest. These
prove the check would notice if the application's reducer stopped agreeing -
a check that only ever ran the reference would pass whatever the application
did, which is the vacuous leg #42 was about.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run  # noqa: E402
from frameshift.orchestration import replay as application  # noqa: E402

REPRODUCES = "evals/fixtures/replay-reproduces-the-snapshot.case.json"
FROM_SNAPSHOT = "evals/fixtures/replay-from-snapshot.case.json"
OUT_OF_ORDER = "evals/fixtures/replay-out-of-order-is-refused.case.json"


def check(case_path: str) -> list[str]:
    """Evaluate a case the way the runner does, with artifacts resolved beside the fixtures."""
    return run.evaluate(run.load(case_path))


class TheCheckMeasuresTheApplication(unittest.TestCase):
    def test_the_reference_cases_pass_with_the_application_agreeing(self) -> None:
        for path in (REPRODUCES, FROM_SNAPSHOT, OUT_OF_ORDER):
            self.assertEqual(check(path), [], path)

    def test_an_application_reducer_that_drops_an_event_type_is_reported(self) -> None:
        real_apply = application._apply

        def drifted(state: dict, event: dict) -> None:
            if event["type"] == "statement.status.changed":
                return  # the silent skip ADR-0013 forbids
            real_apply(state, event)

        with mock.patch.object(application, "_apply", drifted):
            findings = check(REPRODUCES)
        self.assertTrue(any("application reducer reached" in item for item in findings), findings)

    def test_an_application_reducer_that_refuses_a_good_history_is_reported(self) -> None:
        def refuse(*args, **kwargs):
            raise application.ReplayRefused(application.INVARIANT_VIOLATION, "refusing everything")

        with mock.patch.object(application, "fold", refuse):
            findings = check(REPRODUCES)
        self.assertTrue(any("refused a history the reference folded" in item for item in findings), findings)

    def test_an_application_that_folds_what_the_reference_refuses_is_reported(self) -> None:
        """Dropping sequence 2 removes statement.added, so the reference cannot classify it."""
        with mock.patch.object(application, "resume", lambda state, cursor, events, **kw: dict(state)):
            findings = check("evals/fixtures/replay-from-snapshot-gap.case.json")
        self.assertTrue(any("folded a history the reference refused" in item for item in findings), findings)

    def test_an_application_that_accepts_a_broken_sequence_is_reported(self) -> None:
        with mock.patch.object(application, "sequence_violations", lambda events, cursor=0: []):
            findings = check(OUT_OF_ORDER)
        self.assertTrue(any("accepts the sequence the reference refuses" in item for item in findings), findings)


if __name__ == "__main__":
    unittest.main()
