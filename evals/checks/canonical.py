"""Canonicalization and digests for portable checkpoints (ADR-0004).

Reference implementation of the canonicalization rules the checkpoint spec
fixes: UTF-8, sorted object keys, normalized line endings, set-like arrays
ordered, no NaN or Infinity, and a `sha256:` prefixed digest. Execution
metadata is stripped before hashing, so latency, token counts, and provider
request IDs never change semantic identity.

The eval harness owns this so digest stability is verifiable before the
persistence layer exists; the encoder in the application is measured against
the reference checkpoint this module hashes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re

# Arrays the schemas mark `uniqueItems: true` are sets, so their order carries
# no meaning and must not carry into the digest. `evals/test_checks.py` asserts
# this list still matches `schemas/`.
SET_LIKE_FIELDS = frozenset(
    {
        "data_classes",
        "fixtures",
        "invariants",
        "operations",
        "requested_capabilities",
        "required_checkpoints",
        "secondary_roles",
        "source_ids",
        "tool_trace_digests",
        "unsupported_capabilities",
    }
)

# Execution metadata: real, worth keeping, and never part of semantic identity.
#
# Excluded by LOCATION, not by name. These names are dropped at the top level of
# the checkpoint envelope only, and `execution_summaries` takes its whole subtree
# with it — that is where latency, token counts, and provider request IDs live.
#
# The previous rule dropped these names at any depth, which reached into
# canonical state and removed `state.approvals[*].created_at`: an approval's
# recorded time could be rewritten with every digest staying silent. ADR-0002
# makes the approval record — when it was given, bound to what, at which
# revision — the security-relevant artifact, so it has to be inside the digest.
# If a new execution field appears, add it here and confirm it lives in the
# envelope; do not restore a name filter that recurses.
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

# Rule 5 of the canonicalization contract (#22): timestamps are normalized to
# one RFC 3339 UTC spelling before hashing. `2026-07-15T09:14:00Z`, the same
# instant as `...+00:00`, as `...00.000Z`, and as the lowercase form, was
# producing four different digests. Approval times sit inside the state digest
# since #101, so the spelling was inside it too.
#
# Identified by VALUE, not by field name — a name filter at depth is what #101
# had to undo, and an instant is recognizable from its own text. Only a strict
# full match is touched, so prose that merely contains digits and colons is
# left byte-identical.
TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def normalize_timestamp(value: str) -> str:
    """One spelling per instant: UTC, `Z`-suffixed, trailing zero fractions dropped.

    A non-zero fractional second is information and is preserved.
    """
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
        fraction = f"{moment.microsecond:06d}".rstrip("0")
        return moment.strftime("%Y-%m-%dT%H:%M:%S.") + fraction + "Z"
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# A checkpoint cannot contain its own digests.
SELF_DIGEST_FIELDS = frozenset({"checkpoint_digest", "state_digest"})


class CanonicalizationError(ValueError):
    """The value cannot be canonicalized, so it cannot be hashed."""


def canonicalize(value: object, *, drop: frozenset[str] = frozenset()) -> object:
    """Return the semantic core of `value` in a form with exactly one encoding.

    `drop` names keys removed at the top level of `value` and nowhere deeper, so
    an exclusion is a statement about one location rather than about a word.
    """
    if isinstance(value, dict):
        return {
            key: canonicalize(item)
            for key, item in sorted(value.items())
            if key not in drop
        }
    if isinstance(value, list):
        return [canonicalize(item, drop=drop) for item in value]
    if isinstance(value, str):
        return normalize_timestamp(value.replace("\r\n", "\n").replace("\r", "\n"))
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalizationError("NaN and Infinity are not canonical JSON")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    raise CanonicalizationError(f"not canonical JSON: {type(value).__name__}")


def _order_sets(value: object, *, field: str | None = None) -> object:
    if isinstance(value, dict):
        return {key: _order_sets(item, field=key) for key, item in value.items()}
    if isinstance(value, list):
        items = [_order_sets(item) for item in value]
        if field in SET_LIKE_FIELDS:
            return sorted(items, key=lambda item: encode(item))
        return items
    return value


def encode(value: object) -> str:
    """The one textual encoding of a canonical value."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: object, *, drop: frozenset[str] = frozenset()) -> str:
    """`sha256:` digest over the canonicalized value."""
    canonical = _order_sets(canonicalize(value, drop=drop))
    return "sha256:" + hashlib.sha256(encode(canonical).encode("utf-8")).hexdigest()


def state_digest(checkpoint: dict) -> str:
    """Digest of the canonical state a checkpoint carries.

    Nothing is excluded: state holds no execution metadata, and an approval's
    `created_at` is state.
    """
    return digest(checkpoint["state"])


def checkpoint_digest(checkpoint: dict) -> str:
    """Digest of the whole checkpoint envelope, excluding its own digest fields."""
    return digest(checkpoint, drop=ENVELOPE_EXECUTION_METADATA | SELF_DIGEST_FIELDS)


def artifact_digest(payload: bytes) -> str:
    """Digest of a referenced artifact's bytes, which are opaque and not canonicalized."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()
