#!/usr/bin/env python3
"""Dependency-free FrameShift contract invariant evaluator.

Each case file under a discovered root declares the named check that evaluates
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
CORPUS = ROOT / "corpus"

sys.path.insert(0, str(ROOT))

from evals.checks import REGISTRY  # noqa: E402


def load(relative: str, case_dir: Path | None = None) -> object:
    """Load a case artifact beside the case; static contract resources stay rooted."""
    if case_dir:
        repository_resources = ("schemas/", "adapters/", "prompts/", "docs/")
        if relative.startswith(repository_resources):
            candidate = ROOT / relative
        else:
            candidate = case_dir / relative
    else:
        candidate = ROOT / relative
    with candidate.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(case: dict, loader=None) -> list[str]:
    name = case.get("check")
    if name is None:
        return ["case declares no check: add \"check\": \"<name>\""]
    check = REGISTRY.get(name)
    if check is None:
        return [f"unknown check: {name} (known: {sorted(REGISTRY)})"]
    if loader is None:
        loader = lambda reference: load(
            reference[len("evals/fixtures/"):] if reference.startswith("evals/fixtures/") else reference,
            FIXTURES,
        )
    return check(case, loader)


def discover_cases(roots: list[Path]) -> list[Path]:
    """Return case files from roots, rejecting duplicate IDs across roots."""
    found = sorted(path for root in roots for path in root.glob("**/*.case.json") if path.is_file())
    by_id: dict[str, Path] = {}
    duplicates: list[str] = []
    for path in found:
        with path.open("r", encoding="utf-8") as handle:
            case_id = json.load(handle).get("id", path.name)
        if case_id in by_id:
            duplicates.append(f"duplicate case id {case_id!r}: {by_id[case_id]} and {path}")
        else:
            by_id[case_id] = path
    if duplicates:
        raise ValueError("; ".join(duplicates))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    parser.add_argument("--root", action="append", type=Path, help="case root (repeatable)")
    args = parser.parse_args()

    results = []
    roots = args.root or [FIXTURES, CORPUS]
    try:
        paths = discover_cases([p if p.is_absolute() else ROOT / p for p in roots])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"discovery error: {exc}")
        return 1
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            case = json.load(handle)
        errors = evaluate(case, lambda reference, directory=path.parent: load(reference, directory))
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
