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
| `checkpoint_digest` | A committed reference checkpoint hashes to a recorded `sha256:` value, and the value survives key order, line endings, set-like array order, and execution metadata. |
| `checkpoint_integrity` | A copy mutated at one of three levels — canonical state, checkpoint envelope, referenced artifact — is refused with `checkpoint_integrity_failed`, and a verified restore commits and executes nothing. |
| `engine_result_repair` | Repair is attempted once and only for shape: outcome and attempt count are asserted, and the repaired output's identifiers, evidence references, and proposal kinds must be a subset of the invalid output's. |

Runtime adapters should capture actual `EngineResult` JSON and feed it to the
same named checks rather than adding a second entry point.

## The reference checkpoint

`fixtures/reference.checkpoint.json` is the golden artifact: every later
adapter, encoder, and migration is measured against its digests. Its
canonicalization rules live in `checks/canonical.py`, and the `validate`
workflow hashes it on Linux, macOS, and Windows so "the same digest
everywhere" is a CI result rather than a claim.

Changing it changes the recorded digests in
`fixtures/checkpoint-digest-stability.case.json`. If a change is semantic that
is correct; if it is not, the canonicalization rules are wrong.
## The repair corpus

`fixtures/repair/` holds the invalid engine outputs and the candidate repairs
the corpus runs them through. Each case pins the prompt under test by path, id,
and version, so the corpus cannot silently start measuring a different prompt.

The rule the corpus exists for is the subset rule in `checks/repair.py`: a
repaired artifact may gain structure, but every identifier, evidence reference,
and proposal kind in it must already have been in the invalid output. Schema
validation alone cannot catch an invented referent, because the repaired output
is valid by construction.

`checks/schema.py` validates against the committed schemas rather than
restating them, and refuses a schema using a keyword it does not implement, so
silence never passes for a check that did not run.
