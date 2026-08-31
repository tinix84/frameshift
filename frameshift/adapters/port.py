"""The runtime adapter interface (#4, #19, ADR-0001).

An adapter turns a canonical execution request into whatever its runtime speaks,
and turns the answer back into an `EngineResult` plus an execution envelope. #19
lists nine responsibilities for one; this port enforces the three that can be
enforced from outside, without knowing anything about the runtime:

- the request it is handed is valid, so an adapter never has to guess what a
  malformed one meant;
- the result it returns is schema-valid, and the envelope says so honestly —
  an adapter reporting `valid` while returning something invalid is caught here
  rather than downstream;
- the execution it answers is the execution it was asked about, and it adds no
  domain facts of its own.

The rest — capability discovery, delimiting untrusted content, one repair
attempt, never committing a proposal — are properties of the adapter's own
behavior, measured by the conformance corpus rather than by this wrapper.

`EchoAdapter` is the stub #26 said was acceptable for the first slice: the
assertion is about the comparison, not about model output, so an adapter that
returns a committed result exercises every rule above without a provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from frameshift.validation import validate_against

REQUEST_SCHEMA = "execution-request.schema.json"
ENVELOPE_SCHEMA = "execution-envelope.schema.json"
RESULT_SCHEMA = "engine-result.schema.json"

RUNTIME_OUTPUT_INVALID = "runtime_output_invalid"
INVARIANT_VIOLATION = "invariant_violation"
SCHEMA_INVALID = "schema_invalid"


@dataclass
class ExecutionOutcome:
    """What an adapter returns: the proposal, and how the run went."""

    result: dict
    envelope: dict
    violations: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.violations


@runtime_checkable
class Adapter(Protocol):
    """What a runtime adapter must provide. Nothing here mentions a provider."""

    id: str
    version: str

    def capabilities(self) -> dict:
        """The capability manifest this adapter offers, as `capability-manifest.schema.json`."""

    def execute(self, request: dict) -> ExecutionOutcome:
        """Run one engine step and return a normalized outcome."""


def run(adapter: Adapter, request: dict) -> ExecutionOutcome:
    """Validate in, execute, validate out. Returns the outcome; raises nothing."""
    invalid_request = validate_against(request, REQUEST_SCHEMA)
    if invalid_request:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{SCHEMA_INVALID}: request {item}" for item in invalid_request],
        )

    outcome = adapter.execute(request)
    violations = list(outcome.violations)

    violations.extend(
        f"{SCHEMA_INVALID}: envelope {item}"
        for item in validate_against(outcome.envelope, ENVELOPE_SCHEMA)
    )
    invalid_result = validate_against(outcome.result, RESULT_SCHEMA)
    violations.extend(f"{RUNTIME_OUTPUT_INVALID}: {item}" for item in invalid_result)

    # An envelope claiming a clean run while the result does not validate is the
    # one lie this wrapper can catch on its own, and the one most worth catching.
    claimed = outcome.envelope.get("validation", {}).get("outcome")
    if invalid_result and claimed in ("valid", "repaired"):
        violations.append(
            f"{INVARIANT_VIOLATION}: envelope reports {claimed!r} for a result that does not validate"
        )

    for label, document in (("result", outcome.result), ("envelope", outcome.envelope)):
        answered = document.get("execution_id")
        if answered != request["execution_id"]:
            violations.append(
                f"{INVARIANT_VIOLATION}: {label} answers execution {answered!r}, "
                f"the request asked about {request['execution_id']!r}"
            )

    if outcome.result.get("engine") != request["engine"]:
        violations.append(
            f"{INVARIANT_VIOLATION}: result is from engine "
            f"{outcome.result.get('engine')!r}, the request asked {request['engine']!r}"
        )
    if outcome.result.get("input_revision") != request["session_revision"]:
        violations.append(
            f"{INVARIANT_VIOLATION}: result is against revision "
            f"{outcome.result.get('input_revision')!r}, the request pinned "
            f"{request['session_revision']!r}"
        )

    return ExecutionOutcome(outcome.result, outcome.envelope, violations)


class EchoAdapter:
    """A stub that answers with a committed result, normalizing it to the request.

    It contacts nothing. Normalizing means carrying the request's execution id
    and pinned revision onto the answer — which is exactly what a real adapter
    does after a provider replies, and exactly what the port then checks.
    """

    id = "frameshift.echo"
    version = "0.1.0"

    def __init__(self, result: dict, manifest: dict | None = None) -> None:
        self._result = result
        self._manifest = manifest or {}

    def capabilities(self) -> dict:
        return self._manifest

    def execute(self, request: dict) -> ExecutionOutcome:
        result = dict(self._result)
        result["execution_id"] = request["execution_id"]
        result["engine"] = request["engine"]
        result["input_revision"] = request["session_revision"]
        envelope = {
            "schema_version": "1.0.0",
            "execution_id": request["execution_id"],
            "adapter": {"id": self.id, "version": self.version},
            "runtime": {"id": "echo.static", "version": "1"},
            "stop_reason": "complete",
            "validation": {"outcome": "valid", "repair_attempts": 0, "violations": []},
        }
        return ExecutionOutcome(result=result, envelope=envelope)
