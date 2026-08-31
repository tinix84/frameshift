"""The one place an error code comes from (#24).

#24 publishes the application error vocabulary. `approval.py` has always said
"nothing new is invented" about it, and four codes were invented anyway. The
codes were not the problem so much as the absence of anywhere to declare one:
nothing distinguished a deliberate extension from a string somebody reached for
without checking the list.

So there are two sets. PUBLISHED mirrors #24 and is not ours to grow. EXTENSIONS
is ours, and every entry carries the reason no published code fits — a rationale
is the price of an extension. `evals/test_errors.py` asserts every code any
check emits belongs to one of the two.
"""

from __future__ import annotations

# Mirrored from #24's "Errors" section. Changing this set means changing that
# contract, not this file.
PUBLISHED = frozenset(
    {
        "approval_required",
        "approval_stale",
        "capability_unavailable",
        "checkpoint_integrity_failed",
        "data_class_not_allowed",
        "invariant_violation",
        "revision_conflict",
        "runtime_output_invalid",
        "schema_invalid",
        "tool_policy_denied",
    }
)

# Codes the harness adds, each with the reason a published code would misreport
# the condition. An entry here is a deliberate act with an argument attached.
EXTENSIONS = {
    "adapter_state_diverged": (
        "A conformance verdict, not an application error: no API surface returns it, "
        "and it describes two adapters disagreeing rather than one request failing."
    ),
    "capability_downgrade_refused": (
        "Neither capability_unavailable nor tool_policy_denied fits: the capability is "
        "offered and nothing is being executed. What is refused is restoring into a "
        "profile whose approval gate is weaker than the one the checkpoint recorded."
    ),
    "checkpoint_limits_exceeded": (
        "A resource guard that runs before validation. Reporting it as "
        "checkpoint_integrity_failed would call an oversized checkpoint corrupt, and "
        "would make a real corruption indistinguishable from a large file."
    ),
}

VOCABULARY = PUBLISHED | frozenset(EXTENSIONS)

# Published codes the checks use, named so a check imports rather than spells.
APPROVAL_REQUIRED = "approval_required"
APPROVAL_STALE = "approval_stale"
CHECKPOINT_INTEGRITY_FAILED = "checkpoint_integrity_failed"
INVARIANT_VIOLATION = "invariant_violation"

# Extensions the checks use.
ADAPTER_STATE_DIVERGED = "adapter_state_diverged"
CAPABILITY_DOWNGRADE_REFUSED = "capability_downgrade_refused"
CHECKPOINT_LIMITS_EXCEEDED = "checkpoint_limits_exceeded"
