"""Integrity checks for self-contained exemplar directories."""

from __future__ import annotations

from .engine_result import engine_result_invariants
from .schema import load_schema, validate, validate_engine_result
from datetime import date


def corpus_exemplar(case: dict, load) -> list[str]:
    errors: list[str] = []
    try:
        citation = load("citation.json")
        intake = load("intake.json")
        result = load(case["artifact"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return errors + [f"corpus artifact could not be loaded: {exc}"]
    if not isinstance(citation, dict):
        return errors + ["citation must be an object"]
    required = ("relationship", "inspired_by", "source_url", "title", "access_date", "note")
    for field in required:
        if not isinstance(citation.get(field), str) or not citation[field].strip():
            errors.append(f"citation missing non-empty {field}")
    if not isinstance(citation.get("source_url"), str) or not citation["source_url"].startswith("https://"):
        errors.append("citation source_url must be an https URL")
    if citation.get("relationship") != "inspired_by":
        errors.append("citation relationship must be inspired_by")
    if citation.get("inspired_by") != citation.get("source_url"):
        errors.append("citation inspired_by must identify the source URL")
    try:
        date.fromisoformat(citation.get("access_date", ""))
    except (TypeError, ValueError):
        errors.append("citation access_date must be an ISO date")
    if not isinstance(intake, dict):
        errors.append("intake must be an object")
    else:
        errors.extend(f"intake violates session statement schema at {item}" for item in validate(intake, load_schema("session.schema.json")["$defs"]["statement"], current="session.schema.json"))
    if not isinstance(intake, dict) or not intake.get("id"):
        errors.append("intake missing statement id")
    if not isinstance(result, dict):
        errors.append("reference result must be an object")
    else:
        violations = validate_engine_result(result)
        errors.extend(f"reference result violates engine-result schema at {item}" for item in violations)
        if not violations:
            errors.extend(engine_result_invariants(case, load))
    return errors
