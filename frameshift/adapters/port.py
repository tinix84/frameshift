"""The runtime adapter interface (#4, #19, ADR-0001).

An adapter turns a canonical execution request into whatever its runtime speaks,
and turns the answer back into an `EngineResult` plus an execution envelope. #19
lists nine responsibilities for one; this port enforces the parts observable
at the release boundary without knowing anything about the runtime:

- the request it is handed is valid, so an adapter never has to guess what a
  malformed one meant;
- the result it returns is schema-valid, and the envelope says so honestly —
  an adapter reporting `valid` while returning something invalid is caught here
  rather than downstream;
- the execution it answers is the execution it was asked about, and it adds no
  domain facts of its own.

Prompt identity and bounded input are enforced before release. The wrapper
constructs the eight-part reasoning context and passes it separately from the
canonical request. Capability discovery, repair behavior, and never committing
a proposal remain conformance properties of the client.

`EchoAdapter` is the stub #26 said was acceptable for the first slice: the
assertion is about the comparison, not about model output, so an adapter that
returns a committed result exercises every rule above without a provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from frameshift.validation import validate_against
from frameshift.validation.prompts import (
    MalformedFrontMatter,
    body_digest,
    execution_identity_violations,
    input_violations,
    parse_front_matter,
    request_invariant_violations,
    task_frame_sections,
)

REQUEST_SCHEMA = "execution-request.schema.json"
ENVELOPE_SCHEMA = "execution-envelope.schema.json"
RESULT_SCHEMA = "engine-result.schema.json"
REASONING_CONTEXT_SCHEMA = "reasoning-context.schema.json"

CAPABILITY_UNAVAILABLE = "capability_unavailable"
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


@dataclass(frozen=True)
class ExecutionInputs:
    """Trusted prompt resources and resolved untrusted artifacts for one run."""

    prompt_text: str
    published_prompts: list[dict]
    resolved_inputs: dict[str, bytes]
    input_policy: dict[str, int] | None = None


@runtime_checkable
class Adapter(Protocol):
    """What a runtime adapter must provide. Nothing here mentions a provider."""

    id: str
    version: str

    def capabilities(self) -> dict:
        """The capability manifest this adapter offers, as `capability-manifest.schema.json`."""

    def execute(self, request: dict, reasoning_context: dict) -> ExecutionOutcome:
        """Run one engine step and return a normalized outcome."""


def unsupported(requested: list[str], manifest: dict) -> list[str]:
    """Requested capabilities this manifest does not actually offer.

    A capability declared but marked `available: false` counts as unsupported —
    `adapters/claude-code/capabilities.json` declares `external.connector` that
    way, and an engine asking for it must be told, not quietly ignored.
    """
    offered = {
        item["id"]: item
        for item in manifest.get("capabilities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return sorted(
        name for name in requested
        if name not in offered or not offered[name].get("available")
    )


def run(adapter: Adapter, request: dict, inputs: ExecutionInputs) -> ExecutionOutcome:
    """Validate and bound inputs, execute once, then validate the completed record."""
    invalid_request = validate_against(request, REQUEST_SCHEMA)
    if invalid_request:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{SCHEMA_INVALID}: request {item}" for item in invalid_request],
        )

    try:
        prompt_manifest = parse_front_matter(inputs.prompt_text)
    except MalformedFrontMatter as exc:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{INVARIANT_VIOLATION}: prompt manifest is malformed: {exc}"],
        )
    prompt_violations = execution_identity_violations(
        request,
        prompt_manifest,
        body_digest(inputs.prompt_text),
        inputs.published_prompts,
    )
    prompt_engine = prompt_manifest.get("engine")
    if prompt_engine not in (request["engine"], "shared"):
        prompt_violations.append("prompt engine does not match the requested engine")
    declared_output = prompt_manifest.get("output_schema")
    if declared_output is not None and declared_output != request["output_schema"]:
        prompt_violations.append("output_schema does not match the prompt contract")
    prompt_violations.extend(
        request_invariant_violations(
            request,
            {prompt_manifest.get("id"): prompt_manifest},
        )
    )
    if prompt_violations:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{INVARIANT_VIOLATION}: {item}" for item in prompt_violations],
        )
    boundary_violations = input_violations(
        request.get("context", []),
        inputs.resolved_inputs,
        prompt_manifest,
        inputs.input_policy,
    )
    if boundary_violations:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{INVARIANT_VIOLATION}: {item}" for item in boundary_violations],
        )

    try:
        sections = task_frame_sections(inputs.prompt_text)
    except ValueError as exc:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{INVARIANT_VIOLATION}: prompt task frame is invalid: {exc}"],
        )
    reasoning_context = {
        "role": sections["role"],
        "trusted_instructions": sections["trusted_instructions"],
        "untrusted_data": {
            "instructions": sections["untrusted_data"],
            "sources": [
                {**reference, "content": inputs.resolved_inputs[reference["id"]].decode("utf-8")}
                for reference in request.get("context", [])
            ],
        },
        "approved_state": {
            "session_revision": request["session_revision"],
            "state_digest": request["input_state_digest"],
            "instructions": sections["approved_state"],
        },
        "task": sections["task"],
        "output": {"instructions": sections["output"], "schema": request["output_schema"]},
        "invariants": {"instructions": sections["invariants"], "rules": request.get("invariants", [])},
        "failure_behavior": sections["failure_behavior"],
    }
    invalid_context = validate_against(reasoning_context, REASONING_CONTEXT_SCHEMA)
    if invalid_context:
        return ExecutionOutcome(
            result={},
            envelope={},
            violations=[f"{SCHEMA_INVALID}: reasoning context {item}" for item in invalid_context],
        )
    outcome = adapter.execute(request, reasoning_context)
    violations = list(outcome.violations)

    violations.extend(
        f"{SCHEMA_INVALID}: envelope {item}"
        for item in validate_against(outcome.envelope, ENVELOPE_SCHEMA)
    )
    expected_prompt = {
        "id": request["prompt_contract_id"],
        "version": request["prompt_contract_version"],
        "digest": request["prompt_contract_digest"],
    }
    if outcome.envelope.get("prompt_contract") != expected_prompt:
        violations.append(
            f"{INVARIANT_VIOLATION}: completed record does not preserve the request's prompt identity"
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
    # #19 responsibility 9: return unsupported capabilities explicitly. An engine
    # asking for something the runtime cannot do must hear so — silence reads as
    # "it was done". The envelope may name more than this (a connector down
    # today is real and only the adapter knows), so it must cover this set, not
    # equal it.
    requested = [
        name for name in outcome.result.get("requested_capabilities", []) if isinstance(name, str)
    ]
    if requested:
        missing = unsupported(requested, adapter.capabilities())
        reported = set(outcome.envelope.get("unsupported_capabilities", []))
        for name in missing:
            if name not in reported:
                violations.append(
                    f"{CAPABILITY_UNAVAILABLE}: the result requests {name!r}, which this adapter "
                    "does not offer, and the envelope does not report it as unsupported"
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

    def execute(self, request: dict, reasoning_context: dict) -> ExecutionOutcome:
        result = dict(self._result)
        result["execution_id"] = request["execution_id"]
        result["engine"] = request["engine"]
        result["input_revision"] = request["session_revision"]
        envelope = {
            "schema_version": "2.0.0",
            "execution_id": request["execution_id"],
            "prompt_contract": {
                "id": request["prompt_contract_id"],
                "version": request["prompt_contract_version"],
                "digest": request["prompt_contract_digest"],
            },
            "adapter": {"id": self.id, "version": self.version},
            "runtime": {"id": "echo.static", "version": "1"},
            "stop_reason": "complete",
            "validation": {"outcome": "valid", "repair_attempts": 0, "violations": []},
            "unsupported_capabilities": unsupported(
                [name for name in result.get("requested_capabilities", []) if isinstance(name, str)],
                self._manifest,
            ),
        }
        return ExecutionOutcome(result=result, envelope=envelope)
