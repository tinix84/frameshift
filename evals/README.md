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
  "artifact": "framing-solution-disguised.result.json",
  "expect": { "min_rationale_summaries": 2 }
}
```

Artifact paths are resolved relative to the directory containing the case.
This makes a case directory portable. Contract resources such as schemas and
adapter manifests are loaded explicitly from the repository by the checks that
own them.

By default discovery recursively reads both `evals/fixtures/` and `corpus/`.
Use `--root <directory>` to select a root, or repeat the flag for several roots.
For example, the negative self-test root runs with
`python evals/run.py --root evals/selftest`.
Duplicate case IDs are a hard error naming both locations. A corpus directory
contains a narrative, a canonical intake statement, an EngineResult, a case,
and a citation with `relationship: inspired_by`, source URL, title, access date,
and a note distinguishing invented details from the source's contribution.

The runner resolves `check` against `REGISTRY` in `checks/__init__.py` and holds
no check logic itself. An unknown or missing check name fails the case with a
named error; it is never skipped.

Adding a check: write `checks/<name>.py` exposing a
`fn(case, load) -> list[str]` — an empty list is a pass — and add one `REGISTRY`
entry. The runner does not change.

| Check | Evaluates |
|---|---|
| `engine_result_invariants` | Engine-result envelope: required proposal kinds, required checkpoints, minimum rationale summaries and uncertainties, no approval proposals. |
| `approval_binding` | A guarded transition is attempted with a declared approval and must be accepted, or refused with `approval_required`, `approval_stale`, or `invariant_violation`. |
| `checkpoint_digest` | A committed reference checkpoint hashes to a recorded `sha256:` value, and the value survives key order, line endings, set-like array order, and execution metadata. |
| `checkpoint_integrity` | A copy mutated at one of three levels — canonical state, checkpoint envelope, referenced artifact — is refused with `checkpoint_integrity_failed`, and a verified restore commits and executes nothing. |
| `engine_result_repair` | Repair is attempted once and only for shape: outcome and attempt count are asserted, and the repaired output's identifiers, evidence references, and proposal kinds must be a subset of the invalid output's. |
| `prompt_identity` | Installed prompt content and all three request pins match one independently published identity. |
| `reasoning_context` | Resolved inputs stay source-labelled, fit one aggregate bound, and reach the client only inside the eight-part task frame. |
| `prompt_restore` | An intact checkpoint remains inspectable when prompt identity is unavailable, while new reasoning requires exact published pins and a recorded version change. |

Runtime adapters should capture actual `EngineResult` JSON and feed it to the
same named checks rather than adding a second entry point.

Version-1 execution and prompt schemas remain available for inspecting earlier
records. New execution examples use the version-2 request and envelope, whose
ID, version, and digest pins must agree with each other and the published
release record. `reference.reasoning-context.json` shows the eight parts handed
to a client; source content occurs only below `untrusted_data.sources`.

Engine-result expectations are optional. In addition to the positive
expectations shown above, `expected_ladder_levels` requires at least one
abstraction-ladder proposal with exactly the declared sequence of ranked levels.
For example, `["component", "product"]` protects a component-to-product reframe
against missing, reversed, or substituted rungs.

A case may also declare `forbidden_proposal_kinds`,
`forbid_checkpoints`, `max_abstraction_level`, and
`min_missing_information`. The abstraction ladder ordering is explicit:
`component < subsystem < system < product < business`. The current session
schema has exactly this ladder set. Lateral values belong in `system_boundary`
and cause a validation error if used as an abstraction level in a ceiling
comparison. Legacy version-1 checkpoints retain their original schema.

`min_missing_information` is a floor for hand-authored reference artifacts,
not a quality measure. Counting entries rewards padding once real engine output
is evaluated.

## The reference checkpoint

The `replay_equivalence` check folds the reference JSONL history to this same
golden checkpoint. A case with `snapshot` starts from that artifact's state and
event cursor, and replays only the remaining log suffix. The snapshot's state
digest must verify; the suffix must be contiguous, stay in the same session,
and cannot skip or roll back a revision. The starting snapshot remains unchanged.
Cases can mutate a copy of the suffix with `drop`, `swap`, or `revision` to
demonstrate refusal. This is state-replay evidence, not proof of atomic storage
commits or of the full checkpoint admission path.

`fixtures/reference.checkpoint.json` is the golden artifact: every later
adapter, encoder, and migration is measured against its digests. Its
canonicalization rules live in `checks/canonical.py`, and the `validate`
workflow currently hashes it on Windows. Cross-platform digest agreement is
not currently exercised by CI.

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

## The approval gates

`fixtures/approval/gates.session.json` is a schema-valid starting state holding
one target for each of the eight checkpoint gates in `CONTEXT.md`. A case
declares a list of attempts; each runs against a fresh copy of that state, so no
attempt can inherit another's outcome.

An attempt names a gate, a target, and either an approval or none, and expects
`accepted` or a refusal with a stable code. It may also declare an `edit`
applied before the attempt, which is how a sign-off is shown not to carry across
a change to what was signed.

Negative attempts outnumber positive ones, so `approval-gates-accept-a-bound-approval`
carries `"covers_gates": true` — every one of the eight gates must have an
accepted attempt, or the case fails. Refusing everything is not a pass.

Who may pass which gate is `GATE_AUTHORITY` in `checks/approval.py`: the first
slice's reference policy, deliberately visible. Separation-of-duty rules are #16.
