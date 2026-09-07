#!/usr/bin/env python3
"""Assert that each negative expectation is caught by the evaluator."""

from __future__ import annotations

import json
import subprocess
import sys


EXPECTED = {
    "selftest-forbidden-proposal-kinds": "forbidden proposal kinds",
    "selftest-forbid-checkpoints": "forbidden checkpoints",
    "selftest-max-abstraction-level": "exceeds maximum",
    "selftest-min-missing-information": "missing information entries",
}


def main() -> int:
    result = subprocess.run(
        [sys.executable, "evals/run.py", "--root", "evals/selftest", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 1:
        print(f"negative evaluator returned {result.returncode}, expected 1")
        return 1
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"negative evaluator did not emit JSON: {exc}")
        return 1
    if report.get("passed") != 0 or report.get("total") != len(EXPECTED):
        print(f"negative evaluator report is not zero of four: {report}")
        return 1
    results = {item.get("case"): item for item in report.get("results", [])}
    if set(results) != set(EXPECTED):
        print(f"negative evaluator cases changed: {sorted(results)}")
        return 1
    for case_id, fragment in EXPECTED.items():
        errors = results[case_id].get("errors", [])
        if not any(fragment in error for error in errors):
            print(f"{case_id} did not report {fragment!r}: {errors}")
            return 1
    print("negative expectation self-test passed: four deliberate violations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
