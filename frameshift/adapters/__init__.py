"""The runtime adapter port: one normalized way in, one normalized way out."""

from .port import Adapter, EchoAdapter, ExecutionOutcome, run, unsupported

__all__ = ["Adapter", "EchoAdapter", "ExecutionOutcome", "run", "unsupported"]
