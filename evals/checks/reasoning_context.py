"""Bounded reasoning-context enforcement at the client-release seam (#168)."""

import hashlib
from pathlib import Path

from frameshift.adapters import EchoAdapter, ExecutionInputs, run
from frameshift.bootstrap import published_identities

ROOT = Path(__file__).resolve().parents[2]


def reasoning_context(case: dict, load) -> list[str]:
    request = load(case["request"])
    result = load(case["result"])
    prompt_text = (ROOT / case["prompt"]["path"]).read_text(encoding="utf-8")
    references = request.get("context", [])
    resolved = {
        reference["id"]: (ROOT / reference["uri"]).read_bytes()
        for reference in case.get("resolved_inputs", [])
    }
    policy = None
    mutation = case.get("mutation")
    if mutation == "aggregate_overflow":
        payloads = {"art_a": b"1234", "art_b": b"5678"}
        request["context"] = [
            {
                "id": identifier,
                "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "media_type": "text/plain",
            }
            for identifier, payload in payloads.items()
        ]
        resolved = payloads
        policy = {"max_input_bytes": 7, "max_json_depth": 64}
    elif mutation == "drop_media_type":
        request["context"][0].pop("media_type", None)
    elif mutation is not None:
        return [f"unknown reasoning-context mutation {mutation!r}"]

    outcome = run(
        EchoAdapter(result),
        request,
        ExecutionInputs(
            prompt_text,
            published_identities(ROOT / "prompts" / "releases"),
            resolved,
            policy,
        ),
    )
    actual = "accepted" if outcome.accepted else "refused"
    expected = case["expect"]["outcome"]
    errors: list[str] = []
    if actual != expected:
        errors.append(f"reasoning context is {actual}, expected {expected}: {outcome.violations}")
    fragment = case["expect"].get("violation_contains")
    if fragment and not any(fragment in item for item in outcome.violations):
        errors.append(f"expected a violation naming {fragment!r}, got {outcome.violations}")
    return errors
