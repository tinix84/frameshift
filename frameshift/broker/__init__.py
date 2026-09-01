"""The capability broker port: authorize, then execute, then trust nothing."""

from .audit import record, record_violations
from .port import (
    APPROVAL_REQUIRED,
    APPROVAL_STALE,
    CAPABILITY_UNAVAILABLE,
    DATA_CLASS_NOT_ALLOWED,
    TOOL_POLICY_DENIED,
    accept_result,
    authorize,
    needs_approval,
    request_digest,
)

__all__ = [
    "APPROVAL_REQUIRED",
    "APPROVAL_STALE",
    "CAPABILITY_UNAVAILABLE",
    "DATA_CLASS_NOT_ALLOWED",
    "TOOL_POLICY_DENIED",
    "accept_result",
    "record",
    "record_violations",
    "authorize",
    "needs_approval",
    "request_digest",
]
