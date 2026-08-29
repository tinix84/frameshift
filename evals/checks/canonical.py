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

import hashlib
import json

# Arrays the schemas mark `uniqueItems: true` are sets, so their order carries
# no meaning and must not carry into the digest. `evals/test_checks.py` asserts
# this list still matches `schemas/`.
SET_LIKE_FIELDS = frozenset(
    {
        "data_classes",
        "operations",
        "requested_capabilities",
        "required_checkpoints",
        "secondary_roles",
        "source_ids",
    }
)

# Execution metadata: real, worth keeping, and never part of semantic identity.
EXECUTION_METADATA_FIELDS = frozenset(
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

# A checkpoint cannot contain its own digests.
SELF_DIGEST_FIELDS = frozenset({"checkpoint_digest", "state_digest"})


class CanonicalizationError(ValueError):
    """The value cannot be canonicalized, so it cannot be hashed."""


def canonicalize(value: object, *, drop: frozenset[str] = EXECUTION_METADATA_FIELDS) -> object:
    """Return the semantic core of `value` in a form with exactly one encoding."""
    if isinstance(value, dict):
        return {
            key: canonicalize(item, drop=drop)
            for key, item in sorted(value.items())
            if key not in drop
        }
    if isinstance(value, list):
        return [canonicalize(item, drop=drop) for item in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
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


def digest(value: object, *, drop: frozenset[str] = EXECUTION_METADATA_FIELDS) -> str:
    """`sha256:` digest over the canonicalized value."""
    canonical = _order_sets(canonicalize(value, drop=drop))
    return "sha256:" + hashlib.sha256(encode(canonical).encode("utf-8")).hexdigest()


def state_digest(checkpoint: dict) -> str:
    """Digest of the canonical state a checkpoint carries."""
    return digest(checkpoint["state"])


def checkpoint_digest(checkpoint: dict) -> str:
    """Digest of the whole checkpoint envelope, excluding its own digest fields."""
    return digest(checkpoint, drop=EXECUTION_METADATA_FIELDS | SELF_DIGEST_FIELDS)


def artifact_digest(payload: bytes) -> str:
    """Digest of a referenced artifact's bytes, which are opaque and not canonicalized."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()
