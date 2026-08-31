"""The application's canonical encoder (#2, #22, ADR-0004).

This is deliberately a second implementation. `evals/checks/canonical.py` is the
reference the harness owns, written so digest stability was verifiable before
any application existed; its docstring says the application encoder is measured
against the reference checkpoint it hashes. Two independent implementations that
agree on a digest are evidence. One implementation imported twice is not.

Where they differ is where the second implementation earns its keep: the
reference hard-codes the set-like fields and asserts the list still matches
`schemas/`, while this derives them from `schemas/` directly. The schemas are
the structural authority, so an encoder that reads them cannot drift from them
— and if the two ever disagree about which arrays are sets, the conformance
case fails rather than one of them being quietly wrong.

The seven canonicalization rules are #22's, in order: UTF-8 JSON; sorted object
keys; set-like arrays ordered; no NaN or Infinity; RFC 3339 UTC timestamps; the
documented nondeterministic fields excluded from the state digest; SHA-256 with
a `sha256:` prefix.
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import json
import re
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"

# Rule 6, by location and never by name at depth. These are dropped at the top
# level of the checkpoint envelope only; `execution_summaries` takes its whole
# subtree with it. A name filter that recursed once removed
# `state.approvals[*].created_at` from the digest, which is why this is a
# location and not a vocabulary.
ENVELOPE_EXECUTION_METADATA = frozenset(
    {
        "created_at",
        "execution_summaries",
        "latency_ms",
        "provider_request_id",
        "request_id",
        "streaming_chunks",
        "token_counts",
    }
)
SELF_DIGEST_FIELDS = frozenset({"checkpoint_digest", "state_digest"})

# Rule 5. Only a strict full match is normalized, so prose that merely contains
# digits and colons keeps its bytes.
TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


class CanonicalizationError(ValueError):
    """The value cannot be canonicalized, so it cannot be hashed."""


@functools.lru_cache(maxsize=1)
def set_like_fields() -> frozenset[str]:
    """Rule 3, read from `schemas/` rather than restated.

    An array the schemas mark `uniqueItems: true` is a set, so its order carries
    no meaning and must not reach the digest.
    """
    found: set[str] = set()

    def walk(node: object, key: str | None = None) -> None:
        if isinstance(node, dict):
            if node.get("type") == "array" and node.get("uniqueItems") and key:
                found.add(key)
            for name, value in node.items():
                walk(value, name)
        elif isinstance(node, list):
            for value in node:
                walk(value, key)

    for path in sorted(SCHEMAS.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return frozenset(found)


def normalize_timestamp(value: str) -> str:
    """One spelling per instant: UTC, `Z`-suffixed, trailing zero fractions dropped."""
    if not TIMESTAMP.match(value):
        return value
    try:
        moment = datetime.datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return value
    if moment.tzinfo is None:
        return value
    moment = moment.astimezone(datetime.timezone.utc)
    if moment.microsecond:
        return (
            moment.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{moment.microsecond:06d}".rstrip("0")
            + "Z"
        )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def canonicalize(value: object, *, drop: frozenset[str] = frozenset()) -> object:
    """The semantic core of `value`, in a form with exactly one encoding.

    `drop` removes keys at the top level of `value` and nowhere deeper, so an
    exclusion states a location rather than a word.
    """
    sets = set_like_fields()

    def convert(node: object, field: str | None, top: bool) -> object:
        if isinstance(node, dict):
            return {
                key: convert(item, key, False)
                for key, item in sorted(node.items())
                if not (top and key in drop)
            }
        if isinstance(node, list):
            items = [convert(item, None, False) for item in node]
            if field in sets:
                return sorted(items, key=encode)
            return items
        if isinstance(node, str):
            return normalize_timestamp(node.replace("\r\n", "\n").replace("\r", "\n"))
        if isinstance(node, float):
            if node != node or node in (float("inf"), float("-inf")):
                raise CanonicalizationError("NaN and Infinity are not canonical JSON")
            return node
        if node is None or isinstance(node, (bool, int)):
            return node
        raise CanonicalizationError(f"not canonical JSON: {type(node).__name__}")

    return convert(value, None, True)


def encode(value: object) -> str:
    """Rules 1 and 2: the one textual encoding of a canonical value."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: object, *, drop: frozenset[str] = frozenset()) -> bytes:
    """The bytes a digest is taken over, exposed so a caller can persist them."""
    return encode(canonicalize(value, drop=drop)).encode("utf-8")


def digest(value: object, *, drop: frozenset[str] = frozenset()) -> str:
    """Rule 7."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value, drop=drop)).hexdigest()


def state_digest(checkpoint: dict) -> str:
    """Digest of the canonical state. Nothing is excluded: state holds no execution metadata."""
    return digest(checkpoint["state"])


def checkpoint_digest(checkpoint: dict) -> str:
    """Digest of the envelope, excluding execution metadata and its own digests."""
    return digest(checkpoint, drop=ENVELOPE_EXECUTION_METADATA | SELF_DIGEST_FIELDS)


def artifact_digest(payload: bytes) -> str:
    """A referenced artifact's bytes are opaque and are not canonicalized."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()
