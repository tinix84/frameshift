#!/usr/bin/env python3
"""Tests for the story-map grid generator.

Placement and rendering are pure over a list of issues, so the whole grid is
testable without a network. `gh` is the caller's problem and stays out of these.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "story_grid.py"


def module():
    spec = importlib.util.spec_from_file_location("story_grid", GENERATOR)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def issue(number: int, columns: list[str], milestone: str | None = "M1", title: str = "A story"):
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in ["story", *columns]],
        "milestone": {"title": milestone} if milestone else None,
    }


class BackboneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = module()

    def test_nine_columns_are_read_from_the_map(self) -> None:
        columns = self.grid.backbone()
        self.assertEqual(len(columns), 9)
        self.assertIn(("column:reframe", "Get reframed"), columns)

    def test_the_columns_are_in_backbone_order(self) -> None:
        labels = [label for label, _ in self.grid.backbone()]
        self.assertEqual(labels[0], "column:request")
        self.assertEqual(labels[-1], "column:promote")

    def test_the_reader_cannot_silently_return_nothing(self) -> None:
        """An empty backbone would render a grid with no columns and no error."""
        self.assertTrue(self.grid.backbone())


class PlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = module()
        self.columns = [label for label, _ in self.grid.backbone()]

    def test_a_well_formed_story_lands_in_one_cell(self) -> None:
        cells, slices, unplaced = self.grid.place([issue(7, ["column:reframe"])], self.columns)
        self.assertEqual(cells, {("M1", "column:reframe"): [7]})
        self.assertEqual(slices, ["M1"])
        self.assertEqual(unplaced, [])

    def test_a_story_with_no_column_is_listed_not_dropped(self) -> None:
        cells, _, unplaced = self.grid.place([issue(8, [])], self.columns)
        self.assertEqual(cells, {})
        self.assertTrue(any("#8" in item and "0 column labels" in item for item in unplaced))

    def test_a_story_in_two_columns_is_listed_not_dropped(self) -> None:
        _, _, unplaced = self.grid.place(
            [issue(9, ["column:reframe", "column:decide"])], self.columns
        )
        self.assertTrue(any("2 column labels" in item for item in unplaced))

    def test_a_story_with_no_milestone_is_listed_not_dropped(self) -> None:
        _, _, unplaced = self.grid.place([issue(10, ["column:carry"], milestone=None)], self.columns)
        self.assertTrue(any("no milestone" in item for item in unplaced))

    def test_an_unknown_column_label_does_not_place_the_story(self) -> None:
        _, _, unplaced = self.grid.place([issue(11, ["column:invented"])], self.columns)
        self.assertTrue(unplaced)

    def test_several_stories_share_a_cell(self) -> None:
        cells, _, _ = self.grid.place(
            [issue(3, ["column:decide"]), issue(1, ["column:decide"])], self.columns
        )
        self.assertEqual(cells[("M1", "column:decide")], [1, 3])

    def test_slices_are_sorted(self) -> None:
        _, slices, _ = self.grid.place(
            [issue(1, ["column:decide"], "M2"), issue(2, ["column:decide"], "M1")], self.columns
        )
        self.assertEqual(slices, ["M1", "M2"])


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = module()
        self.columns = self.grid.backbone()

    def test_a_column_with_no_stories_renders_an_empty_cell(self) -> None:
        """Visible coverage gaps are the whole point of a map over a list."""
        cells, slices, unplaced = self.grid.place([issue(7, ["column:reframe"])], [c for c, _ in self.columns])
        text = self.grid.render(cells, slices, self.columns, unplaced)
        row = next(line for line in text.splitlines() if line.startswith("| M1 |"))
        self.assertEqual(row.count("|"), len(self.columns) + 2)
        self.assertIn("#7", row)
        self.assertIn("|  |", row)

    def test_every_column_title_appears_in_the_header(self) -> None:
        text = self.grid.render({}, [], self.columns, [])
        for _, title in self.columns:
            self.assertIn(title, text)

    def test_unplaced_stories_are_shown_under_the_grid(self) -> None:
        text = self.grid.render({}, [], self.columns, ["#8 A story — no milestone"])
        self.assertIn("## Unplaced stories", text)
        self.assertIn("#8", text)

    def test_no_unplaced_stories_says_so(self) -> None:
        self.assertIn("No unplaced stories.", self.grid.render({}, [], self.columns, []))

    def test_the_output_says_not_to_commit_it(self) -> None:
        self.assertIn("Do not commit", self.grid.render({}, [], self.columns, []))


class EndToEndTests(unittest.TestCase):
    def test_the_generator_runs_and_prints_a_grid(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR)], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode != 0:
            self.assertIn("gh is unavailable", result.stderr)
            return
        self.assertIn("# Story map grid", result.stdout)
        self.assertIn("Get reframed", result.stdout)

    def test_an_empty_tracker_says_so_on_stderr(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR)], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode == 0 and "no issue carries" in result.stderr:
            self.assertIn("every cell is empty", result.stderr)


class UnplacedDiagnosisTests(unittest.TestCase):
    """Name the label that failed, not only the count."""

    def setUp(self):
        self.grid = module()
        self.columns = [label for label, _ in self.grid.backbone()]

    def test_a_misspelt_label_is_named(self):
        _, _, unplaced = self.grid.place([issue(1, ["column:typo"])], self.columns)
        self.assertTrue(any("unknown column label" in item for item in unplaced), unplaced)
        self.assertTrue(any("column:typo" in item for item in unplaced), unplaced)

    def test_no_label_still_reports_the_count(self):
        _, _, unplaced = self.grid.place([issue(2, [])], self.columns)
        self.assertTrue(any("0 column labels" in item for item in unplaced), unplaced)

    def test_two_labels_still_reports_the_count(self):
        _, _, unplaced = self.grid.place(
            [issue(3, ["column:reframe", "column:decide"])], self.columns
        )
        self.assertTrue(any("2 column labels" in item for item in unplaced), unplaced)

    def test_a_missing_milestone_is_still_named(self):
        _, _, unplaced = self.grid.place([issue(4, ["column:carry"], None)], self.columns)
        self.assertTrue(any("no milestone" in item for item in unplaced), unplaced)

if __name__ == "__main__":
    unittest.main()
