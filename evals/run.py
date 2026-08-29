#!/usr/bin/env python3
"""Dependency-free FrameShift contract invariant evaluator.

Each case file under `evals/fixtures/` declares the named check that evaluates
it. The runner resolves the name against `evals.checks.REGISTRY` and reports one
pass/fail line per case; it holds no check logic of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"

sys.path.insert(0, str(ROOT))

from evals.checks import REGISTRY  # noqa: E402


def load(relative: str) -> object:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(case: dict) -> list[str]:
    name = case.get("check")
    if name is None:
        return ["case declares no check: add \"check\": \"<name>\""]
    check = REGISTRY.get(name)
    if check is None:
        return [f"unknown check: {name} (known: {sorted(REGISTRY)})"]
    return check(case, load)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args()

    results = []
    for path in sorted(FIXTURES.glob("*.case.json")):
        case = load(str(path.relative_to(ROOT)))
        errors = evaluate(case)
        results.append({"case": case["id"], "passed": not errors, "errors": errors})

    passed = sum(item["passed"] for item in results)
    report = {"passed": passed, "total": len(results), "results": results}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in results:
            marker = "PASS" if item["passed"] else "FAIL"
            print(f"{marker} {item['case']}")
            for error in item["errors"]:
                print(f"  - {error}")
        print(f"{passed}/{len(results)} fixtures passed")
    return 0 if passed == len(results) and results else 1


if __name__ == "__main__":
    sys.exit(main())
