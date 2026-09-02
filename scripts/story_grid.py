#!/usr/bin/env python3
"""Render the story-map grid from tracker labels (#73).

The grid is the volatile half of the story map and must never be hand-copied.
The tracker is the source of truth; this is a view over it — the same
relationship the project already asserts between structured state and a
rendered diagram.

**Where the output goes, and why.** To stdout. #73 left the choice between
printing, a gitignored path, and committing, and ruled out the third itself:
committing re-introduces a stale copy of data that already exists, which is the
second-tracker failure this design rejects. Between the remaining two, stdout
needs no gitignore entry, no path to agree on, and no file to go stale if
someone forgets to regenerate it. Anyone who wants a file can redirect one, and
it will be as fresh as the moment they asked.

Columns come from the backbone table in `docs/story-map.md`; slices from the
milestone each issue carries. An unplaced story is listed under the grid rather
than dropped, and a cell with no stories renders empty, because visible
coverage gaps are the whole point of a map over a list.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY_MAP = ROOT / "docs" / "story-map.md"
COLUMN_ROW = re.compile(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*`column:([a-z-]+)`\s*\|", re.MULTILINE)
COLUMN_PREFIX = "column:"


def backbone() -> list[tuple[str, str]]:
    """(label, title) for each column, read from the map's backbone table."""
    text = STORY_MAP.read_text(encoding="utf-8")
    section = text.partition("## The backbone")[2].partition("## Slices")[0]
    return [(f"{COLUMN_PREFIX}{slug}", title) for title, slug in COLUMN_ROW.findall(section)]


def fetch_stories() -> list[dict] | None:
    """Open `story` issues, or None when `gh` cannot answer."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", "story", "--state", "open",
             "--limit", "300", "--json", "number,title,labels,milestone"],
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


def place(issues: list[dict], columns: list[str]) -> tuple[dict, list[str], list[str]]:
    """Sort issues into (slice, column) cells, and say what could not be placed."""
    known = set(columns)
    grid: dict[tuple[str, str], list[int]] = {}
    slices: list[str] = []
    unplaced: list[str] = []

    for issue in sorted(issues, key=lambda item: item["number"]):
        number = issue["number"]
        labels = {item["name"] for item in issue.get("labels", [])}
        placed = sorted(labels & known)
        milestone = (issue.get("milestone") or {}).get("title")

        # Named before the guard, not inside it: an issue carrying one valid
        # label *and* a misspelt one has exactly one known label, so a guard on
        # the count alone would place it in a cell and never mention the typo.
        # The validator errors on that issue (story_placement_errors), and a
        # view that draws what the rule rejects is worse than no view.
        unknown = sorted(name for name in labels if name.startswith(COLUMN_PREFIX) and name not in known)

        if unknown or len(placed) != 1 or not milestone:
            # Name the label that failed rather than only counting: an issue
            # carrying `column:typo` reads as "0 column labels", which sends the
            # reader looking for a missing label instead of a misspelt one.
            if unknown:
                reason = f"unknown column labels {', '.join(unknown)}"
            elif len(placed) != 1:
                reason = f"{len(placed)} column labels"
            else:
                reason = "no milestone"
            unplaced.append(f"#{number} {issue['title']} — {reason}")
            continue
        if milestone not in slices:
            slices.append(milestone)
        grid.setdefault((milestone, placed[0]), []).append(number)

    return grid, sorted(slices), unplaced


def render(grid: dict, slices: list[str], columns: list[tuple[str, str]], unplaced: list[str]) -> str:
    """The grid as markdown. Empty cells are the point, not an omission."""
    titles = [title for _, title in columns]
    lines = [
        "# Story map grid",
        "",
        "Generated from tracker labels. Do not commit this; regenerate it.",
        "",
        "| Slice | " + " | ".join(titles) + " |",
        "|---" * (len(titles) + 1) + "|",
    ]
    for slice_name in slices or ["(no slice)"]:
        cells = []
        for label, _ in columns:
            numbers = grid.get((slice_name, label), [])
            cells.append(" ".join(f"#{number}" for number in numbers))
        lines.append(f"| {slice_name} | " + " | ".join(cells) + " |")

    lines.append("")
    if unplaced:
        lines.append("## Unplaced stories")
        lines.append("")
        lines.extend(f"- {item}" for item in unplaced)
    else:
        lines.append("No unplaced stories.")
    return "\n".join(lines) + "\n"


def main() -> int:
    columns = backbone()
    if not columns:
        print("cannot read the backbone table in docs/story-map.md", file=sys.stderr)
        return 1

    issues = fetch_stories()
    if issues is None:
        print("gh is unavailable, so the grid cannot be generated", file=sys.stderr)
        return 1

    grid, slices, unplaced = place(issues, [label for label, _ in columns])
    print(render(grid, slices, columns, unplaced), end="")
    if not issues:
        print(
            "note: no issue carries the `story` label yet, so every cell is empty",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
