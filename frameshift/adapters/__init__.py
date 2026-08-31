"""The runtime adapter port: one normalized way in, one normalized way out."""

from .port import Adapter, ExecutionOutcome, EchoAdapter, run

__all__ = ["Adapter", "EchoAdapter", "ExecutionOutcome", "run"]
