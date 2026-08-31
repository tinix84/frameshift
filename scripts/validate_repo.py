#!/usr/bin/env python3
"""Fast dependency-free structural checks for the FrameShift repository."""

from __future__ import annotations

import json
import re
import subprocess
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
# A prose term is allowed on a line that explicitly forbids it, and on that line
# only. Naming what you refuse to do is the point; being near a negation is not.
#
# Every marker here is a phrase whose job in a sentence is to forbid. Bare
# negations — `no `, `not `, `cannot` — are deliberately absent: `not` is one of
# the commonest words in English, so any nearby negation would silence the term
# it sits beside. For the same reason the marker is searched in the line alone
# and never in the enclosing heading, which used to exempt a whole section.
PROHIBITION_MARKERS = [
    "must not",
    "never",
    "forbid",
    "prohibit",
    "non-goal",
    "instead of",
    "rather than",
]
# Files a machine reads, where a key or value naming a forbidden term is the
# violation regardless of the surrounding prose.
MACHINE_READABLE_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml"}
# Where state is defined, behavior is requested, and agents are instructed.
COT_SCAN_DIRS = ["schemas", "prompts", "evals/fixtures", "adapters"]
COT_ROOT_FILES = ["README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md"]
# The shape of an engine result, for a fixture that does not name its engine.
ENGINE_RESULT_MARKER_KEYS = ("execution_id", "proposals")
# Exempt: these must name the thing they prohibit in order to define it.
COT_EXEMPT = ["docs/adr", "CONTEXT.md"]

# #21: no credential material in prompts, checkpoints, or logs. Same shape as
# ADR-0007's prohibition and it degrades the same way, one plausible field name
# at a time — an `api_key` added to a capability manifest with good intentions
# would pass every other check.
#
# These terms name the *material*, never the topic, and that distinction is the
# whole reason the list is short:
#   - bare `token` is excluded: `token_counts` is a real field in the reference
#     checkpoint's execution summaries.
#   - bare `credential` is excluded: #21 says a capability declares its
#     credential owner, so `credential_owner` is a field this contract expects.
# A check that fired on either would be switched off within a week.
CREDENTIAL_TERMS = [
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "bearer_token",
    "client_secret",
    "passwd",
    "password",
    "private_key",
    "refresh_token",
    "secret_key",
]
# Values that are credential material whatever field they hide behind.
CREDENTIAL_VALUES = [
    "-----BEGIN ",
    "AKIA",
    "ghp_",
    "xoxb-",
]
# These state the prohibition, so they may name it — as `docs/adr/` may for
# chain-of-thought.
CREDENTIAL_EXEMPT = ["CONTRIBUTING.md", "SECURITY.md"]
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
        machine_readable = path.suffix in MACHINE_READABLE_SUFFIXES
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            if machine_readable:
                for term in FORBIDDEN_FIELD_TERMS:
                    if term in lowered.replace("-", "_"):
                        errors.append(f"chain-of-thought term in {relative}:{number}: {term}")
                continue
            match = PROSE_PATTERN.search(line)
            if not match:
                continue
            if any(marker in lowered for marker in PROHIBITION_MARKERS):
                continue
            errors.append(f"chain-of-thought term in {relative}:{number}: {match.group(0)}")
    return errors


def is_engine_result(artifact: object) -> bool:
    """An engine result, recognized without trusting it to name its own engine.

    Keying on `engine` alone let a fixture opt out of the whole check by
    omitting that key, so the shape an engine result cannot fake — an execution
    carrying proposals — identifies it too.
    """
    if not isinstance(artifact, dict):
        return False
    return "engine" in artifact or all(key in artifact for key in ENGINE_RESULT_MARKER_KEYS)


def credential_material_errors() -> list[str]:
    """#21: no credential material where state is defined or behavior requested."""
    errors: list[str] = []
    for path in scan_paths():
        relative = path.relative_to(ROOT).as_posix()
        if relative in CREDENTIAL_EXEMPT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower().replace("-", "_")
            for term in CREDENTIAL_TERMS:
                if term in lowered:
                    errors.append(f"credential material in {relative}:{number}: {term}")
            for marker in CREDENTIAL_VALUES:
                if marker in line:
                    errors.append(f"credential material in {relative}:{number}: {marker.strip()}")
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
        if not is_engine_result(artifact):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if "engine" not in artifact:
            errors.append(f"engine result without a named engine: {relative}")
        if not artifact.get("rationale_summaries"):
            errors.append(f"engine result without rationale summaries: {relative}")
    return errors


# The story map is the durable half of the roadmap: the North Star and the shape
# of the journey. Two properties keep it honest. It must declare a North Star and
# a backbone, because a map with neither is a wish; and every exemplar it names
# must have a runnable twin in the harness, because — as the file itself puts it
# — an exemplar nobody can execute is an anecdote.
#
# The third check #72 asks for, that every `story`-labelled issue carries exactly
# one journey-position label and one milestone, is not here. It needs the tracker
# and the `column:*` label set, and no `story` issue exists yet; a check that
# matches nothing manufactures confidence. See #72.
STORY_MAP = "docs/story-map.md"
STORY_MAP_SECTIONS = ["## North Star", "## The backbone", "## Exemplars"]
EXEMPLAR = re.compile(r"^\|\s*`(?P<name>[a-z0-9][a-z0-9-]*)`\s*\|", re.MULTILINE)


def story_map_errors() -> list[str]:
    """The story map declares a North Star and a backbone, and names no anecdotes."""
    path = ROOT / STORY_MAP
    if not path.is_file():
        return [f"missing required file: {STORY_MAP}"]

    text = path.read_text(encoding="utf-8")
    errors = [
        f"{STORY_MAP} is missing a {section!r} section"
        for section in STORY_MAP_SECTIONS
        if section not in text
    ]

    backbone = text.partition("## The backbone")[2].partition("## Slices")[0]
    if not [line for line in backbone.splitlines() if line.startswith("|")]:
        errors.append(f"{STORY_MAP} declares a backbone with no columns")

    exemplars = EXEMPLAR.findall(text.partition("## Exemplars")[2])
    if not exemplars:
        errors.append(f"{STORY_MAP} names no exemplars")
    fixtures = {path.name for path in (ROOT / "evals" / "fixtures").rglob("*") if path.is_file()}
    for name in exemplars:
        # Where the twin lives is the harness's decision, so the map names the
        # exemplar and the check looks for a fixture carrying that name.
        if not any(item.startswith(name + ".") for item in fixtures):
            errors.append(f"exemplar {name} named in {STORY_MAP} has no fixture under evals/fixtures/")
    return errors


COLUMN_LABEL = re.compile(r"`(column:[a-z-]+)`")


def backbone_columns() -> list[str]:
    """The nine column labels, read from the story map's own backbone table."""
    text = (ROOT / STORY_MAP).read_text(encoding="utf-8")
    backbone = text.partition("## The backbone")[2].partition("## Slices")[0]
    return COLUMN_LABEL.findall(backbone)


def story_placement_errors(issues: list[dict], columns: list[str]) -> list[str]:
    """Every `story` issue sits in exactly one column and exactly one slice.

    Pure over the issue list so it can be tested without a network: the `gh`
    call is the caller's problem, and this is the rule.
    """
    known = set(columns)
    errors: list[str] = []
    for issue in issues:
        number = issue.get("number")
        labels = {item["name"] for item in issue.get("labels", [])}
        placed = sorted(labels & known)
        unknown = sorted({item for item in labels if item.startswith("column:")} - known)
        if unknown:
            errors.append(f"issue #{number} carries unknown column labels {unknown}")
        if len(placed) != 1:
            errors.append(
                f"issue #{number} has {len(placed)} journey-position labels {placed}, expected exactly one"
            )
        if not issue.get("milestone"):
            errors.append(f"issue #{number} is a story with no milestone, so it sits in no slice")
    return errors


def fetch_story_issues() -> list[dict] | None:
    """Open `story` issues, or None when `gh` cannot answer."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", "story", "--state", "open",
             "--limit", "200", "--json", "number,labels,milestone"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def story_tracker_errors() -> list[str]:
    """The third story-map check, skipped with a notice when `gh` is unavailable."""
    if not (ROOT / STORY_MAP).is_file():
        return []  # story_map_errors already reports the missing file
    columns = backbone_columns()
    if len(columns) != 9:
        return [f"{STORY_MAP} declares {len(columns)} column labels, expected nine"]

    issues = fetch_story_issues()
    if issues is None:
        print(f"note: skipping the story placement check, gh is unavailable ({len(columns)} columns declared)")
        return []
    # A check over an empty set passes silently, which is how a checker starts
    # manufacturing confidence. Say how many were examined.
    print(f"note: story placement checked over {len(issues)} open `story` issues")
    return story_placement_errors(issues, columns)


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
    errors.extend(credential_material_errors())
    errors.extend(rationale_summary_errors())
    errors.extend(story_map_errors())
    errors.extend(story_tracker_errors())

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
