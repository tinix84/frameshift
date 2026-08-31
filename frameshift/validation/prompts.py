"""A prompt is a versioned interface, so its manifest is checkable (#20, ADR-0006).

#20 opens with the principle: *"A prompt is a versioned interface, not free-form
application code."* An interface that declares nothing is not one, and a
declaration nobody checks is worse — `prompts/problem-framing.v1.md` names an
output schema and an evaluation fixture, and until now neither reference was
resolved. Rename a fixture and the prompt goes on claiming to be covered by it.

The front matter is a deliberately small subset of YAML: `key: value` and
`key: [a, b]`, one per line, which is all the committed prompts use. A real
parser would be a dependency, and this repository stays installable by clone.
Anything the subset cannot read is reported rather than skipped, so a prompt
cannot smuggle a field past the check by writing it in a shape nobody parses.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
SCHEMA = "prompt-manifest.schema.json"

FRONT_MATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
LINE = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.*?)\s*$")


class MalformedFrontMatter(ValueError):
    """The prompt's front matter is missing or outside the supported subset."""


def parse_front_matter(text: str) -> dict:
    """The manifest at the top of a prompt file, as a dict."""
    match = FRONT_MATTER.match(text)
    if match is None:
        raise MalformedFrontMatter("no front matter block")
    manifest: dict = {}
    for number, line in enumerate(match.group("body").splitlines(), start=1):
        if not line.strip():
            continue
        found = LINE.match(line)
        if found is None:
            raise MalformedFrontMatter(f"line {number} is not `key: value`: {line!r}")
        key, value = found.group("key"), found.group("value")
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            manifest[key] = [item.strip() for item in inner.split(",")] if inner else []
        else:
            manifest[key] = value
    return manifest


def prompt_manifest_violations() -> list[str]:
    """Every prompt declares a valid manifest whose references resolve."""
    from .schema import validate_against

    violations: list[str] = []
    seen: dict[str, str] = {}
    paths = sorted(PROMPTS.glob("*.md"))
    if not paths:
        return ["no prompts found, so the manifest check verifies nothing"]

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        try:
            manifest = parse_front_matter(path.read_text(encoding="utf-8"))
        except MalformedFrontMatter as exc:
            violations.append(f"{relative}: {exc}")
            continue

        violations.extend(f"{relative}: {item}" for item in validate_against(manifest, SCHEMA))

        identifier = manifest.get("id")
        if identifier in seen:
            violations.append(f"{relative}: id {identifier!r} is already declared by {seen[identifier]}")
        elif isinstance(identifier, str):
            seen[identifier] = relative

        output_schema = manifest.get("output_schema")
        if isinstance(output_schema, str) and not (ROOT / output_schema).is_file():
            violations.append(f"{relative}: output_schema {output_schema!r} does not exist")

        for fixture in manifest.get("fixtures", []):
            if not (ROOT / "evals" / "fixtures" / f"{fixture}.case.json").is_file():
                violations.append(f"{relative}: fixture {fixture!r} has no case under evals/fixtures/")

    for path in paths:
        try:
            manifest = parse_front_matter(path.read_text(encoding="utf-8"))
        except MalformedFrontMatter:
            continue
        repair = manifest.get("repair_prompt")
        if isinstance(repair, str) and repair not in seen:
            violations.append(
                f"{path.relative_to(ROOT).as_posix()}: repair_prompt {repair!r} names no committed prompt"
            )
    return violations
