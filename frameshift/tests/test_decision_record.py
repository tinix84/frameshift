#!/usr/bin/env python3
"""Tests for the decision record export (#23 FR-10).

FR-10's acceptance signal is that the export *distinguishes* facts, assumptions,
inference, and approval — not that an export exists. So most of these are about
the partition: every claim lands in exactly one category, no category silently
swallows another, and nothing is dropped.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.export import CATEGORIES, claims, render  # noqa: E402

REFERENCE = ROOT / "evals" / "fixtures" / "reference.checkpoint.json"
GATES = ROOT / "evals" / "fixtures" / "approval" / "gates.session.json"


def reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))["state"]


def gates() -> dict:
    return json.loads(GATES.read_text(encoding="utf-8"))


class PartitionTests(unittest.TestCase):
    """The four categories must partition provenance, not overlap or leak."""

    def test_the_categories_cover_every_provenance_kind(self) -> None:
        schema = json.loads((ROOT / "schemas" / "common.schema.json").read_text(encoding="utf-8"))
        declared = set(schema["$defs"]["provenance"]["properties"]["kind"]["enum"])
        covered = {kind for _, kinds, _ in CATEGORIES for kind in kinds}
        self.assertEqual(covered, declared, "a provenance kind with no heading would vanish")

    def test_no_kind_appears_in_two_categories(self) -> None:
        seen: set[str] = set()
        for _, kinds, _ in CATEGORIES:
            for kind in kinds:
                self.assertNotIn(kind, seen, f"{kind} is claimed by two categories")
                seen.add(kind)

    def test_assumed_is_not_folded_into_established(self) -> None:
        established = next(kinds for heading, kinds, _ in CATEGORIES if heading == "Established")
        self.assertNotIn("assumed", established)
        self.assertNotIn("unknown", established)

    def test_every_category_carries_a_note_saying_what_it_means(self) -> None:
        for heading, _, note in CATEGORIES:
            with self.subTest(heading=heading):
                self.assertGreater(len(note), 20)


class ClaimTests(unittest.TestCase):
    def test_every_claim_in_the_reference_session_is_collected(self) -> None:
        state = reference()
        expected = 1 + len(state["graph"]["nodes"]) + len(state["graph"]["edges"])
        self.assertEqual(len(claims(state)), expected)

    def test_an_edge_is_a_claim_and_reads_as_a_relation(self) -> None:
        found = {item["id"]: item for item in claims(reference())}
        edge = found["edge_001"]
        self.assertEqual(edge["kind"], "inferred")
        self.assertIn("->", edge["text"])
        self.assertIn("Cell price", edge["text"])

    def test_a_claim_without_provenance_is_not_collected(self) -> None:
        """Collecting by provenance is what makes the record auditable."""
        state = reference()
        state["statements"][0].pop("provenance")
        self.assertNotIn("stmt_001", {item["id"] for item in claims(state)})

    def test_an_unrecorded_kind_falls_to_unattributed_not_established(self) -> None:
        state = reference()
        state["statements"][0]["provenance"] = {"source_ids": []}
        found = {item["id"]: item for item in claims(state)}
        self.assertEqual(found["stmt_001"]["kind"], "unknown")

    def test_both_committed_sessions_yield_claims(self) -> None:
        for label, session in (("reference", reference()), ("gates", gates())):
            with self.subTest(session=label):
                self.assertTrue(claims(session))


class RenderTests(unittest.TestCase):
    def test_every_claim_appears_exactly_once(self) -> None:
        state = reference()
        text = render(state)
        for item in claims(state):
            with self.subTest(claim=item["id"]):
                self.assertEqual(text.count(f"**{item['id']}**"), 1)

    def test_every_category_gets_a_heading_even_when_empty(self) -> None:
        text = render(reference())
        for heading, _, _ in CATEGORIES:
            self.assertIn(f"## {heading}", text)
        self.assertIn("Nothing in this category.", text)

    def test_an_approval_shows_who_what_when_and_what_it_was_bound_to(self) -> None:
        text = render(reference())
        section = text.partition("## Approvals")[2]
        self.assertIn("user_lead_eng", section)
        self.assertIn("frame_001", section)
        self.assertIn("2026-07-15T09:14:00Z", section)
        self.assertIn("bound to", section)
        self.assertIn("at revision 4", section)

    def test_a_session_with_no_approval_says_so_plainly(self) -> None:
        text = render(gates())
        self.assertIn("No approval has been recorded", text)

    def test_a_session_with_no_working_frame_says_nothing_is_decided(self) -> None:
        state = reference()
        state.pop("active_frame_id")
        self.assertIn("Nothing here is decided", render(state))

    def test_the_working_frame_is_the_approved_one(self) -> None:
        self.assertIn("How might we reach the 2027 pack cost target", render(reference()))

    def test_cited_sources_are_shown(self) -> None:
        self.assertIn("intake_001", render(reference()))

    def test_the_record_invents_no_prose(self) -> None:
        """Every claim line quotes state; only headings and notes are ours."""
        state = reference()
        text = render(state)
        for item in claims(state):
            with self.subTest(claim=item["id"]):
                self.assertIn(item["text"], text)

    def test_an_assumed_claim_lands_under_assumed(self) -> None:
        state = reference()
        state["statements"][0]["provenance"]["kind"] = "assumed"
        section = render(state).partition("## Assumed")[2].partition("## Unattributed")[0]
        self.assertIn("stmt_001", section)

    def test_the_output_is_ascii_safe_for_a_windows_console(self) -> None:
        for session in (reference(), gates()):
            with self.subTest():
                render(session).encode("cp1252")


if __name__ == "__main__":
    unittest.main()
