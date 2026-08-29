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
    "CLAUDE.md",
    "CONTEXT.md",
    "docs/agents/issue-tracker.md",
    "docs/agents/triage-labels.md",
    "docs/agents/domain.md",
    "schemas/session.schema.json",
    "schemas/checkpoint.schema.json",
]
# Product requirements, contracts, and units of work live in the issue tracker.
# These directories must not come back; see docs/agents/issue-tracker.md.
FORBIDDEN = ["specs", "backlog", "docs/product", "docs/architecture", "docs/reasoning"]

# ADR-0007: private chain-of-thought is never requested, exposed, logged, or
# persisted, and rationale summaries are carried instead. The vocabulary lives
# here, in the open, so a contributor can see what is banned without reading the
# checker.
#
# Field terms are matched as substrings in machine-readable files, where a key or
# value naming one of them *is* the violation. Prose terms are matched as words in
# instruction text, where the same vocabulary is legitimate when a document is
# stating the prohibition — see PROHIBITION_MARKERS.
FORBIDDEN_FIELD_TERMS = [
    "chain_of_thought",
    "chainofthought",
    "reasoning_trace",
    "internal_monologue",
    "scratchpad",
    "thoughts",
    "thinking",
]
FORBIDDEN_PROSE_TERMS = [
    "chain of thought",
    "chain-of-thought",
    "chain_of_thought",
    "reasoning_trace",
    "internal_monologue",
    "inner monologue",
    "scratchpad",
    "step by step",
    "show your reasoning",
    "show your work",
    "think out loud",
    "your thinking",
    "your thoughts",
]
# A prose term is allowed on a line that forbids it, or under a heading that
# frames the section as a prohibition. Naming what you refuse to do is the point.
PROHIBITION_MARKERS = [
    "do not",
    "does not",
    "must not",
    "cannot",
    "never",
    "no ",
    "not ",
    "without",
    "forbid",
    "prohibit",
    "instead of",
    "rather than",
    "non-goal",
]
# Where state is defined, behavior is requested, and agents are instructed.
COT_SCAN_DIRS = ["schemas", "prompts", "evals/fixtures", "adapters"]
COT_ROOT_FILES = ["README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md"]
# Exempt: these must name the thing they prohibit in order to define it.
COT_EXEMPT = ["docs/adr", "CONTEXT.md"]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PROSE_PATTERN = re.compile(
    "|".join(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])" for term in FORBIDDEN_PROSE_TERMS),
    re.IGNORECASE,
)


def is_exempt(relative: str) -> bool:
    return any(relative == item or relative.startswith(item + "/") for item in COT_EXEMPT)


def scan_paths() -> list[Path]:
    """Files ADR-0007 applies to: where state is defined and behavior requested."""
    paths: list[Path] = []
    for directory in COT_SCAN_DIRS:
        paths.extend(sorted(path for path in (ROOT / directory).rglob("*") if path.is_file()))
    paths.extend(ROOT / name for name in COT_ROOT_FILES if (ROOT / name).is_file())
    return [path for path in paths if not is_exempt(path.relative_to(ROOT).as_posix())]


def chain_of_thought_errors() -> list[str]:
    """Fail on chain-of-thought vocabulary, naming file, line, and matched term."""
    errors: list[str] = []
    for path in scan_paths():
        relative = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        machine_readable = path.suffix == ".json"
        heading = ""
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#") and not machine_readable:
                heading = line.lower()
            lowered = line.lower()
            if machine_readable:
                for term in FORBIDDEN_FIELD_TERMS:
                    if term in lowered.replace("-", "_"):
                        errors.append(f"chain-of-thought term in {relative}:{number}: {term}")
                continue
            match = PROSE_PATTERN.search(line)
            if not match:
                continue
            context = lowered + " " + heading
            if any(marker in context for marker in PROHIBITION_MARKERS):
                continue
            errors.append(f"chain-of-thought term in {relative}:{number}: {match.group(0)}")
    return errors


def rationale_summary_errors() -> list[str]:
    """The positive half of ADR-0007: engine results carry rationale summaries."""
    errors: list[str] = []
    for path in sorted((ROOT / "evals" / "fixtures").rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                artifact = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(artifact, dict) or "engine" not in artifact:
            continue
        if not artifact.get("rationale_summaries"):
            relative = path.relative_to(ROOT).as_posix()
            errors.append(f"engine result without rationale summaries: {relative}")
    return errors


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

    for relative in FORBIDDEN:
        if (ROOT / relative).exists():
            errors.append(f"forbidden directory: {relative} (this content belongs in the issue tracker)")

    errors.extend(chain_of_thought_errors())
    errors.extend(rationale_summary_errors())

    adr_paths = sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    if len(adr_paths) < 5:
        errors.append("at least five ADRs are required")

    decision_log = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for path in adr_paths:
        if path.name == "0000-template.md":
            continue
        if path.name not in decision_log:
            errors.append(f"missing decision log row in CLAUDE.md for {path.name}")

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
