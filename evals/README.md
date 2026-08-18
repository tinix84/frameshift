# Evaluation harness

`run.py` is a dependency-free reference harness. It checks portable fixture invariants rather than exact model prose. It currently validates reference artifacts and checkpoint semantics; runtime adapters should add a runner that captures actual `EngineResult` JSON and feeds it to the same invariant evaluator.

Run:

```sh
python evals/run.py
python evals/run.py --json
```

A fixture declares an artifact and expectations such as required proposal kinds, required checkpoints, forbidden approval creation, and minimum rationale/uncertainty counts.
