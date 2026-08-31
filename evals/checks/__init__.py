"""Named checks the eval harness can dispatch to.

A case file declares `"check": "<name>"`; `evals/run.py` looks the name up here
and calls it with the case and a loader. Adding a check means adding one module
and one REGISTRY entry — no change to the runner.

A check receives the parsed case and a `load(relative_path)` callable, and
returns a list of human-readable error strings. An empty list is a pass.
"""

from __future__ import annotations

from .adapter import adapter_round_trip, corpus_across_adapters
from .approval import approval_binding
from .artifacts import artifact_conformance
from .checkpoint import checkpoint_digest, checkpoint_integrity
from .engine_result import engine_result_invariants
from .repair import engine_result_repair
from .schema_files import schema_wellformedness
from .session import session_invariants


REGISTRY = {
    "adapter_round_trip": adapter_round_trip,
    "approval_binding": approval_binding,
    "artifact_conformance": artifact_conformance,
    "corpus_across_adapters": corpus_across_adapters,
    "checkpoint_digest": checkpoint_digest,
    "checkpoint_integrity": checkpoint_integrity,
    "engine_result_invariants": engine_result_invariants,
    "engine_result_repair": engine_result_repair,
    "schema_wellformedness": schema_wellformedness,
    "session_invariants": session_invariants,
}
