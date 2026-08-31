#!/usr/bin/env python3
"""Tests that no check can invent an error code again.

`approval.py` said "nothing new is invented" and four codes were invented
anyway, because nothing enforced it and nowhere existed to declare an exception.
These tests make the next invented code fail here rather than pass review.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.checks import errors  # noqa: E402

CHECKS = Path(__file__).resolve().parents[1] / "evals" / "checks"
# A module-level constant whose value is a bare snake_case string: the shape a
# hand-written error code takes.
BARE_CODE = re.compile(r'^(?P<name>[A-Z][A-Z_]*) = "(?P<value>[a-z]+(?:_[a-z]+)+)"$', re.MULTILINE)


class VocabularyTests(unittest.TestCase):
    def test_published_and_extensions_are_disjoint(self) -> None:
        self.assertEqual(errors.PUBLISHED & frozenset(errors.EXTENSIONS), frozenset())

    def test_the_vocabulary_is_their_union(self) -> None:
        self.assertEqual(errors.VOCABULARY, errors.PUBLISHED | frozenset(errors.EXTENSIONS))

    def test_every_extension_carries_a_rationale(self) -> None:
        for code, reason in errors.EXTENSIONS.items():
            with self.subTest(code=code):
                self.assertIsInstance(reason, str)
                self.assertGreater(len(reason.strip()), 40, f"{code} needs a real reason")

    def test_every_named_constant_is_in_the_vocabulary(self) -> None:
        named = {
            value
            for name, value in vars(errors).items()
            if name.isupper() and isinstance(value, str)
        }
        self.assertTrue(named)
        self.assertEqual(named - errors.VOCABULARY, set())

    def test_the_published_set_matches_the_codes_issue_24_lists(self) -> None:
        """Mirrored by hand from #24; this pins the mirror so a silent edit fails."""
        self.assertEqual(
            errors.PUBLISHED,
            frozenset(
                {
                    "schema_invalid",
                    "invariant_violation",
                    "revision_conflict",
                    "approval_required",
                    "approval_stale",
                    "capability_unavailable",
                    "tool_policy_denied",
                    "data_class_not_allowed",
                    "runtime_output_invalid",
                    "checkpoint_integrity_failed",
                }
            ),
        )


class NoBareCodeTests(unittest.TestCase):
    def test_no_check_module_declares_a_bare_error_code(self) -> None:
        """A code comes from `errors`, so a check imports rather than spells."""
        offenders: list[str] = []
        for path in sorted(CHECKS.glob("*.py")):
            if path.name == "errors.py":
                continue
            text = path.read_text(encoding="utf-8")
            for match in BARE_CODE.finditer(text):
                value = match.group("value")
                if value in errors.VOCABULARY:
                    offenders.append(f"{path.name}: {match.group('name')} = {value!r}")
        self.assertEqual(offenders, [], "declare the code in errors.py and import it")

    def test_the_detector_would_catch_a_reintroduced_code(self) -> None:
        """The scan above is only reassuring if it can actually match."""
        planted = 'DANGLING = "dangling_reference"\n'
        self.assertTrue(BARE_CODE.search('INVARIANT_VIOLATION = "invariant_violation"\n'))
        self.assertFalse(
            BARE_CODE.search(planted).group("value") in errors.VOCABULARY,
            "dangling_reference was replaced by invariant_violation and must not return",
        )


class EmittedCodeTests(unittest.TestCase):
    def test_every_code_a_check_emits_belongs_to_the_vocabulary(self) -> None:
        from evals.checks import adapter, approval, capability, checkpoint, session

        emitted = {
            adapter.DIVERGENCE,
            approval.APPROVAL_REQUIRED,
            approval.APPROVAL_STALE,
            approval.INVARIANT_VIOLATION,
            capability.DOWNGRADE,
            checkpoint.INTEGRITY_VIOLATION,
            checkpoint.LIMIT_VIOLATION,
            session.INVARIANT_VIOLATION,
        }
        self.assertEqual(emitted - errors.VOCABULARY, set())

    def test_a_dangling_reference_reports_the_published_invariant_code(self) -> None:
        from evals.checks import session

        self.assertEqual(session.INVARIANT_VIOLATION, "invariant_violation")
        self.assertNotIn("dangling_reference", errors.VOCABULARY)


if __name__ == "__main__":
    unittest.main()
