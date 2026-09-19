"""The one place an application error code comes from (#24, #127, ADR-0015).

#24 publishes the application error vocabulary and ADR-0015 gives `contracts`
ownership of it. Until now every module re-declared the codes it used as bare
strings, `frameshift/orchestration/api.py` spelled them inline, and two codes
were emitted that #24 never published and nothing declared as extensions. A
mirror in every module is a mirror that drifts; a code spelled where it is
raised is a code nobody checked against the list.

So there are two sets, the same shape `evals/checks/errors.py` gives the
harness. PUBLISHED mirrors #24 and is not ours to grow. EXTENSIONS is ours, and
every entry carries the reason no published code fits — a rationale is the
price of an extension. `evals/test_errors.py` asserts the two PUBLISHED sets
agree, that every code any application module emits belongs to one of the two,
and that no module declares or spells a code of its own.
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

# Codes the application adds, each with the reason a published code would
# misreport the condition. An entry here is a deliberate act with an argument.
EXTENSIONS = {
    "capability_downgrade_refused": (
        "Neither capability_unavailable nor tool_policy_denied fits: the capability is "
        "offered and nothing is being executed. What is refused is restoring into a "
        "profile whose approval gate is weaker, or whose side effect is graver, than "
        "the one the checkpoint recorded."
    ),
    "checkpoint_limits_exceeded": (
        "A resource guard that runs before validation. Reporting it as "
        "checkpoint_integrity_failed would call an oversized checkpoint corrupt, and "
        "would make a real corruption indistinguishable from a large file."
    ),
    "execution_failed": (
        "The executor raised before it returned anything. runtime_output_invalid "
        "would claim there was output to judge; tool_policy_denied would claim the "
        "broker refused it. Neither happened: the call was authorized, it ran, and "
        "it died, which the audit record must say in its own words."
    ),
    "retry_confirmation_required": (
        "A repeated tool call against a capability that does not declare itself "
        "idempotent. approval_required would say the first approval never existed; "
        "approval_stale would say it was bound to older content. Neither is true: the "
        "approval is good and the retry itself is the thing that needs a human."
    ),
    "unsupported_configuration": (
        "The native client or its attested approval profile cannot carry a trusted "
        "confirmation at all (ADR-0014). No approval is missing or stale and no "
        "document is malformed; the runtime is configured such that no confirmation "
        "it produced could be trusted, and the human must be told to fix that first."
    ),
}

VOCABULARY = PUBLISHED | frozenset(EXTENSIONS)

# Published codes, named so a module imports rather than spells.
APPROVAL_REQUIRED = "approval_required"
APPROVAL_STALE = "approval_stale"
CAPABILITY_UNAVAILABLE = "capability_unavailable"
CHECKPOINT_INTEGRITY_FAILED = "checkpoint_integrity_failed"
DATA_CLASS_NOT_ALLOWED = "data_class_not_allowed"
INVARIANT_VIOLATION = "invariant_violation"
REVISION_CONFLICT = "revision_conflict"
RUNTIME_OUTPUT_INVALID = "runtime_output_invalid"
SCHEMA_INVALID = "schema_invalid"
TOOL_POLICY_DENIED = "tool_policy_denied"

# Extensions.
CAPABILITY_DOWNGRADE_REFUSED = "capability_downgrade_refused"
CHECKPOINT_LIMITS_EXCEEDED = "checkpoint_limits_exceeded"
EXECUTION_FAILED = "execution_failed"
RETRY_CONFIRMATION_REQUIRED = "retry_confirmation_required"
UNSUPPORTED_CONFIGURATION = "unsupported_configuration"
