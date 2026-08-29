# Evaluation harness

`run.py` is a dependency-free reference harness. It checks portable fixture
invariants rather than exact model prose.

Run:

```sh
python evals/run.py
python evals/run.py --json
python -m unittest discover -s evals -p "test_*.py" -t .
```

## Cases and named checks

A case file (`<id>.case.json`) declares the named check that evaluates it:

```json
{
  "id": "framing-solution-disguised",
  "check": "engine_result_invariants",
  "artifact": "evals/fixtures/framing-solution-disguised.result.json",
  "expect": { "min_rationale_summaries": 2 }
}
```

The runner resolves `check` against `REGISTRY` in `checks/__init__.py` and holds
no check logic itself. An unknown or missing check name fails the case with a
named error; it is never skipped.

Adding a check: write `checks/<name>.py` exposing a
`fn(case, load) -> list[str]` — an empty list is a pass — and add one `REGISTRY`
entry. The runner does not change.

| Check | Evaluates |
|---|---|
| `engine_result_invariants` | Engine-result envelope: required proposal kinds, required checkpoints, minimum rationale summaries and uncertainties, no approval proposals. |

Runtime adapters should capture actual `EngineResult` JSON and feed it to the
same named checks rather than adding a second entry point.
