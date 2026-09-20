#!/usr/bin/env python3
"""Tests that no check can invent an error code again.

`approval.py` said "nothing new is invented" and four codes were invented
anyway, because nothing enforced it and nowhere existed to declare an exception.
These tests make the next invented code fail here rather than pass review.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.checks import errors  # noqa: E402
from frameshift.contracts import errors as application_errors  # noqa: E402

CHECKS = ROOT / "evals" / "checks"
APPLICATION = ROOT / "frameshift"
# A module-level constant whose value is a bare snake_case string: the shape a
# hand-written error code takes.
BARE_CODE = re.compile(r'^(?P<name>[A-Z][A-Z_]*) = "(?P<value>[a-z]+(?:_[a-z]+)+)"$', re.MULTILINE)
# Constants that take the shape of a code but are not one. Every entry is a
# (path, name) pair so the exemption cannot widen to a whole file, and the
# pairs are pinned by a test so one cannot be added without saying why.
NOT_A_CODE = {("frameshift/mcp/confirmation_server.py", "TOOL_NAME")}
# The shape of a violation string: a code, a colon, a detail.
CODED_MESSAGE = re.compile(r"^(?P<code>[a-z]+(?:_[a-z]+)+): ")
# Functions whose first positional argument is an error code.
EMITTERS = {"Refused", "ReplayRefused", "Refusal", "_pending", "_refused"}


def bare_code_offenders(paths: list[Path]) -> list[str]:
    """Every module-level constant spelling a code, exempting only `NOT_A_CODE`.

    Membership in a vocabulary is deliberately not consulted: filtering on it
    caught a re-spelling of a published code and let a brand-new one through,
    which is the hole #127 named.
    """
    offenders: list[str] = []
    for path in paths:
        try:
            where = path.relative_to(ROOT).as_posix()
        except ValueError:
            where = path.name
        for match in BARE_CODE.finditer(path.read_text(encoding="utf-8")):
            if (where, match.group("name")) in NOT_A_CODE:
                continue
            offenders.append(f"{where}: {match.group('name')} = {match.group('value')!r}")
    return offenders


def _modules(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if path.name != "__init__.py"
        and "tests" not in path.relative_to(ROOT).parts
        and path.name != "errors.py"
    )


def _dotted(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _resolve(module: object, node: ast.AST) -> object:
    """A module-level name, or a dotted attribute of one; `None` if it is neither."""
    if isinstance(node, ast.Name):
        return getattr(module, node.id, None)
    if isinstance(node, ast.Attribute):
        owner = _resolve(module, node.value)
        return getattr(owner, node.attr, None) if owner is not None else None
    return None


def emitted_codes(path: Path) -> tuple[set[str], list[str]]:
    """Every error code a module emits, and every place one is spelled inline.

    An emission is a `"code": <expr>` entry, the first argument to a refusal
    constructor, or a message whose first segment is a code followed by a colon.
    Names are resolved against the imported module so that what is checked is
    the value actually raised, not how the source happened to spell it.
    """
    module = importlib.import_module(_dotted(path))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    codes: set[str] = set()
    inline: list[str] = []

    def emit(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            inline.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {node.value!r}")
            codes.add(node.value)
            return
        value = _resolve(module, node)
        if isinstance(value, str):
            codes.add(value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "code" and value is not None:
                    emit(value)
        elif isinstance(node, ast.Call):
            callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if callee in EMITTERS and node.args:
                emit(node.args[0])
        elif isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            if isinstance(first, ast.FormattedValue) and len(node.values) > 1:
                after = node.values[1]
                if isinstance(after, ast.Constant) and str(after.value).startswith(": "):
                    emit(first.value)
            elif isinstance(first, ast.Constant) and CODED_MESSAGE.match(str(first.value)):
                emit(ast.Constant(CODED_MESSAGE.match(str(first.value)).group("code"), lineno=node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and CODED_MESSAGE.match(node.value):
            emit(ast.Constant(CODED_MESSAGE.match(node.value).group("code"), lineno=node.lineno))
    # A literal inside an f-string is visited twice, once as part of the
    # f-string and once as a constant of its own.
    return codes, list(dict.fromkeys(inline))


class VocabularyTests(unittest.TestCase):
    def test_published_and_extensions_are_disjoint(self) -> None:
        self.assertEqual(errors.PUBLISHED & frozenset(errors.EXTENSIONS), frozenset())

    def test_the_application_publishes_the_same_codes(self) -> None:
        """Two mirrors of #24, one in each half, that cannot drift apart."""
        self.assertEqual(application_errors.PUBLISHED, errors.PUBLISHED)
        self.assertEqual(
            application_errors.VOCABULARY,
            application_errors.PUBLISHED | frozenset(application_errors.EXTENSIONS),
        )
        self.assertEqual(application_errors.PUBLISHED & frozenset(application_errors.EXTENSIONS), frozenset())

    def test_every_application_extension_carries_a_rationale(self) -> None:
        for code, reason in application_errors.EXTENSIONS.items():
            with self.subTest(code=code):
                self.assertGreater(len(reason.strip()), 40, f"{code} needs a real reason")

    def test_the_extensions_both_halves_emit_are_declared_on_both_sides(self) -> None:
        for code in ("checkpoint_limits_exceeded", "capability_downgrade_refused"):
            with self.subTest(code=code):
                self.assertIn(code, errors.EXTENSIONS)
                self.assertIn(code, application_errors.EXTENSIONS)

    def test_every_application_named_constant_is_in_its_vocabulary(self) -> None:
        named = {
            value
            for name, value in vars(application_errors).items()
            if name.isupper() and isinstance(value, str)
        }
        self.assertTrue(named)
        self.assertEqual(named - application_errors.VOCABULARY, set())

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
        """A code comes from `errors`, so a check imports rather than spells.

        Every match is an offender, whether or not the value is already in the
        vocabulary: the version that reported only known values caught a
        re-spelling and let a brand-new code straight through (#127).
        """
        offenders: list[str] = []
        for path in sorted(CHECKS.glob("*.py")):
            if path.name == "errors.py":
                continue
            text = path.read_text(encoding="utf-8")
            for match in BARE_CODE.finditer(text):
                offenders.append(f"{path.name}: {match.group('name')} = {match.group('value')!r}")
        self.assertEqual(offenders, [], "declare the code in errors.py and import it")

    def test_no_application_module_re_declares_a_published_code(self) -> None:
        """The same rule for `frameshift/`, whose codes come from `contracts.errors`.

        Every match is an offender whether or not the value is already in a
        vocabulary. Filtering on membership was the defect #127 named: it caught
        a re-spelling of a known code and let a brand-new invention through.
        """
        offenders = bare_code_offenders(_modules(APPLICATION))
        self.assertEqual(offenders, [], "import the code from frameshift.contracts.errors")

    def test_the_application_detector_catches_an_unpublished_invention(self) -> None:
        """The scan above is only worth running if an unknown value offends too."""
        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "invented.py"
            planted.write_text('NEVER_PUBLISHED = "wholly_invented_code"\n', encoding="utf-8")
            offenders = bare_code_offenders([planted])
        self.assertEqual(len(offenders), 1)
        self.assertIn("NEVER_PUBLISHED", offenders[0])
        self.assertNotIn("wholly_invented_code", application_errors.VOCABULARY | errors.VOCABULARY)

    def test_the_only_exempt_constant_is_the_one_that_is_not_a_code(self) -> None:
        """The exemption is narrow and named, so it cannot quietly grow."""
        self.assertEqual(NOT_A_CODE, {("frameshift/mcp/confirmation_server.py", "TOOL_NAME")})

    def test_the_detector_would_catch_a_reintroduced_code(self) -> None:
        """The scan above is only reassuring if it can actually match."""
        planted = 'DANGLING = "dangling_reference"\n'
        self.assertTrue(BARE_CODE.search('INVARIANT_VIOLATION = "invariant_violation"\n'))
        self.assertFalse(
            BARE_CODE.search(planted).group("value") in errors.VOCABULARY,
            "dangling_reference was replaced by invariant_violation and must not return",
        )


class EmittedCodeTests(unittest.TestCase):
    """Every code any module emits is published or a declared extension (#127).

    The earlier version hand-enumerated eight constants from five modules, so
    a ninth constant in a sixth module was never looked at. These walk every
    emission site the source contains instead.
    """

    def test_every_code_a_check_emits_belongs_to_the_vocabulary(self) -> None:
        emitted: set[str] = set()
        inline: list[str] = []
        for path in _modules(CHECKS):
            codes, spelled = emitted_codes(path)
            emitted |= codes
            inline += spelled
        self.assertTrue(emitted, "the detector found no emission at all")
        self.assertEqual(emitted - errors.VOCABULARY, set(), "declare the code in evals/checks/errors.py")
        self.assertEqual(inline, [], "import the code rather than spelling it where it is raised")

    def test_every_code_the_application_emits_belongs_to_its_vocabulary(self) -> None:
        emitted: set[str] = set()
        inline: list[str] = []
        for path in _modules(APPLICATION):
            codes, spelled = emitted_codes(path)
            emitted |= codes
            inline += spelled
        self.assertTrue(emitted, "the detector found no emission at all")
        self.assertEqual(
            emitted - application_errors.VOCABULARY, set(), "declare the code in frameshift/contracts/errors.py"
        )
        self.assertEqual(inline, [], "import the code rather than spelling it where it is raised")

    def test_the_detector_sees_the_emission_shapes_the_code_uses(self) -> None:
        """Only reassuring if it matches: one site of each shape, found by value."""
        application = set()
        for path in _modules(APPLICATION):
            application |= emitted_codes(path)[0]
        for code in ("approval_required", "checkpoint_limits_exceeded", "unsupported_configuration",
                     "retry_confirmation_required", "revision_conflict"):
            self.assertIn(code, application)
        harness = set()
        for path in _modules(CHECKS):
            harness |= emitted_codes(path)[0]
        for code in ("adapter_state_diverged", "capability_downgrade_refused", "approval_stale"):
            self.assertIn(code, harness)

    def test_an_inline_spelling_is_reported_by_file_and_line(self) -> None:
        planted = ROOT / "evals" / "checks" / "_probe_inline.py"
        planted.write_text(
            'def refuse():\n    return {"code": "frame_axis_incoherent", "detail": ""}\n',
            encoding="utf-8",
        )
        try:
            codes, inline = emitted_codes(planted)
        finally:
            planted.unlink()
            sys.modules.pop("evals.checks._probe_inline", None)
        self.assertEqual(codes, {"frame_axis_incoherent"})
        self.assertEqual(len(inline), 1)
        self.assertIn("_probe_inline.py:2", inline[0])

    def test_a_dangling_reference_reports_the_published_invariant_code(self) -> None:
        from evals.checks import session

        self.assertEqual(session.INVARIANT_VIOLATION, "invariant_violation")
        self.assertNotIn("dangling_reference", errors.VOCABULARY)


if __name__ == "__main__":
    unittest.main()
