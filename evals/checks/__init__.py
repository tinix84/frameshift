"""Named checks the eval harness can dispatch to.

A case file declares `"check": "<name>"`; `evals/run.py` looks the name up here
and calls it with the case and a loader. Adding a check means adding one module
and one REGISTRY entry — no change to the runner.

A check receives the parsed case and a `load(relative_path)` callable, and
returns a list of human-readable error strings. An empty list is a pass.
"""

from __future__ import annotations

from .engine_result import engine_result_invariants
from .repair import engine_result_repair


REGISTRY = {
    "engine_result_invariants": engine_result_invariants,
    "engine_result_repair": engine_result_repair,
}
