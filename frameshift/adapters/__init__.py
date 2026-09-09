"""The runtime adapter port: one normalized way in, one normalized way out."""

from .port import Adapter, EchoAdapter, ExecutionInputs, ExecutionOutcome, run, unsupported

__all__ = ["Adapter", "EchoAdapter", "ExecutionInputs", "ExecutionOutcome", "run", "unsupported"]
