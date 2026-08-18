#!/usr/bin/env python3
"""Fast dependency-free structural checks for the FrameShift repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "LICENSE",
    "AGENTS.md",
    "docs/product/prd.md",
    "docs/architecture/system-architecture.md",
    "docs/reasoning/problem-framing-engine.md",
    "specs/runtime-portability.md",
    "schemas/session.schema.json",
    "schemas/checkpoint.schema.json",
    "backlog/issues.yaml",
]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for path in sorted(ROOT.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(ROOT)}: {exc}")

    for path in sorted(ROOT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"broken link in {path.relative_to(ROOT)}: {target}")

    adr_paths = sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    if len(adr_paths) < 5:
        errors.append("at least five ADRs are required")

    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository validation passed")
    print(f"JSON files: {len(list(ROOT.rglob('*.json')))}")
    print(f"ADRs: {len(adr_paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
