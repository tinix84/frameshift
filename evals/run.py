#!/usr/bin/env python3
"""Dependency-free FrameShift contract invariant evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def load(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(case: dict) -> list[str]:
    artifact = load(ROOT / case["artifact"])
    expect = case["expect"]
    errors: list[str] = []

    if artifact.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    proposal_kinds = {item.get("kind") for item in artifact.get("proposals", [])}
    missing_kinds = set(expect.get("required_proposal_kinds", [])) - proposal_kinds
    if missing_kinds:
        errors.append(f"missing proposal kinds: {sorted(missing_kinds)}")

    checkpoints = set(artifact.get("required_checkpoints", []))
    missing_checkpoints = set(expect.get("required_checkpoints", [])) - checkpoints
    if missing_checkpoints:
        errors.append(f"missing checkpoints: {sorted(missing_checkpoints)}")

    if len(artifact.get("rationale_summaries", [])) < expect.get("min_rationale_summaries", 0):
        errors.append("too few rationale summaries")
    if len(artifact.get("uncertainties", [])) < expect.get("min_uncertainties", 0):
        errors.append("too few uncertainties")

    if expect.get("forbid_approval_proposals", True):
        forbidden = [item for item in artifact.get("proposals", []) if item.get("kind") == "approval"]
        if forbidden:
            errors.append("engine result must not propose approval objects")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args()

    results = []
    for path in sorted(FIXTURES.glob("*.case.json")):
        case = load(path)
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
