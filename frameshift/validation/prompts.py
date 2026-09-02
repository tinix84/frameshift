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

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
SCHEMA = "prompt-manifest.schema.json"

FRONT_MATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
FRONT_MATTER_BLOCK = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
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
            manifest[key] = _flow_list(value[1:-1], number)
        else:
            manifest[key] = value
    return manifest


def _flow_list(inner: str, line: int) -> list[str]:
    """Split a flow sequence, respecting double quotes.

    Splitting on every comma read `"no evidence, requirement, or decision is
    invented"` as three items — a silent misparse, which is worse than a raise
    because the manifest then declares things nobody wrote.

    An item containing a comma must therefore be quoted. Nothing needs to check
    that afterwards: an unquoted comma has already split, so a comma surviving
    inside an item can only have come from a quoted one. An unbalanced quote is
    reported, since that is the one shape this cannot resolve.
    """
    items: list[str] = []
    current = ""
    quoted = False
    for character in inner:
        if character == '"':
            # The quote delimits the item; it is not part of it.
            quoted = not quoted
            continue
        if character == "," and not quoted:
            items.append(current.strip())
            current = ""
        else:
            current += character
    if quoted:
        raise MalformedFrontMatter(f"line {line} has an unbalanced quote")
    if current.strip():
        items.append(current.strip())
    return items


def body_digest(text: str) -> str:
    """Digest of everything below the front matter, line endings normalized.

    The manifest does not digest itself — the same reason a checkpoint omits its
    own digest fields before hashing. Only the prompt text is covered, which is
    the part a version is a promise about.
    """
    body = FRONT_MATTER_BLOCK.sub("", text).replace("\r\n", "\n")
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


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

        declared = manifest.get("body_digest")
        actual = body_digest(path.read_text(encoding="utf-8"))
        if isinstance(declared, str) and declared != actual:
            violations.append(
                f"{relative}: body_digest is {declared}, the prompt text hashes to {actual} — "
                "the body changed without the version changing"
            )

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


def request_invariant_violations(request: dict, installed: dict | None = None) -> list[str]:
    """An execution request carries exactly the invariants its prompt declares (#20).

    The prompt states its invariants and the request tells the engine what to
    satisfy. When those two lists can differ, a request can quietly drop the one
    that mattered — and the prompt would still look like it had promised it.
    """
    from frameshift.persistence.compatibility import installed_prompts

    available = installed_prompts() if installed is None else installed
    prompt_id = request.get("prompt_contract_id")
    manifest = available.get(prompt_id)
    if manifest is None:
        return [f"the request pins prompt {prompt_id!r}, which is not installed here"]

    declared = list(manifest.get("invariants", []))
    carried = list(request.get("invariants", []))
    if not declared:
        return []
    if sorted(carried) != sorted(declared):
        dropped = sorted(set(declared) - set(carried))
        added = sorted(set(carried) - set(declared))
        detail = []
        if dropped:
            detail.append(f"drops {dropped}")
        if added:
            detail.append(f"adds {added}")
        return [
            f"the request's invariants do not match prompt {prompt_id!r}: " + " and ".join(detail)
        ]
    return []

