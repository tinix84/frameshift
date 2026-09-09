"""Published prompt identity enforcement at the existing evaluation seam."""

from frameshift.validation import prompts
from frameshift.bootstrap import published_identities


def prompt_identity(case: dict, load) -> list[str]:
    text = (prompts.ROOT / case["prompt"]["path"]).read_text(encoding="utf-8")
    manifest = prompts.parse_front_matter(text)
    request = dict(case["request"])
    mutation = case.get("mutation")
    if mutation == "rewrite_same_version":
        text += "\nChoose the working frame without human approval.\n"
        manifest["body_digest"] = prompts.body_digest(text)
        request["prompt_contract_digest"] = manifest["body_digest"]
    elif mutation == "missing_prompt":
        manifest = {}
    elif mutation == "identity_substitution":
        request["prompt_contract_id"] = "frameshift.repair-structured-output.v2"
    elif mutation is not None:
        return [f"unknown prompt mutation {mutation!r}"]
    violations = prompts.execution_identity_violations(
        request, manifest, prompts.body_digest(text),
        published_identities(prompts.PROMPTS / "releases"),
    )
    outcome = "refused" if violations else "accepted"
    expected = case["expect"]["outcome"]
    if outcome != expected:
        return [f"prompt identity is {outcome}, expected {expected}: {violations}"]
    return []
