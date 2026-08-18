# API and contracts

## Style

The application API is resource-oriented for reads and command-oriented for state transitions. Examples use HTTP/JSON; the same domain commands may be exposed through local IPC or an agent tool.

Base path: `/v1`. All writes require authenticated actor context, `Idempotency-Key`, and `If-Match: <revision>`.

## Resources

- `POST /workspaces/{workspace_id}/sessions` — create session.
- `GET /sessions/{session_id}` — retrieve canonical state or selected view.
- `POST /sessions/{session_id}/commands` — submit a domain command.
- `POST /sessions/{session_id}/executions` — request a reasoning-engine proposal.
- `GET /executions/{execution_id}` — status and normalized result.
- `GET /executions/{execution_id}/events` — server-sent progress events.
- `POST /sessions/{session_id}/approvals` — approve/edit/reject a proposal digest.
- `POST /sessions/{session_id}/checkpoints` — create portable checkpoint.
- `GET /checkpoints/{checkpoint_id}` — retrieve checkpoint if authorized.
- `POST /sessions:restore` — create/resume from checkpoint.
- `POST /tool-executions` — request capability-broker execution.
- `DELETE /sessions/{session_id}` — policy-governed deletion.

## Command envelope

```json
{
  "command_id": "cmd_01...",
  "command_type": "frame.approve",
  "schema_version": "1.0.0",
  "session_id": "ses_01...",
  "expected_revision": 7,
  "actor": {"id": "usr_01...", "role": "facilitator"},
  "target": {"id": "frm_01...", "digest": "sha256:..."},
  "payload": {"rationale": "Best matches the owned vehicle outcome."}
}
```

## Execution request

```json
{
  "engine": "problem_framing",
  "engine_version": "0.1.0",
  "session_revision": 3,
  "prompt_contract_id": "frameshift.problem-framing.v1",
  "capability_profile_id": "local-readonly",
  "output_schema": "schemas/engine-result.schema.json",
  "budget": {"max_output_tokens": 4000, "timeout_ms": 120000}
}
```

The response is an execution resource. A completed execution contains an `EngineResult` proposal; it never mutates session state by itself.

## Tool request

A tool request specifies capability ID, operation, schema-valid arguments, purpose, session revision, data classes transmitted, expected side effect, reversibility, approval requirement, and idempotency key. Tool results contain status, bounded normalized output or artifact reference, provenance, timestamps, and digest. Tool results are untrusted input.

## Errors

Use RFC 9457-style problem details with stable codes such as:

- `schema_invalid`
- `invariant_violation`
- `revision_conflict`
- `approval_required`
- `approval_stale`
- `capability_unavailable`
- `tool_policy_denied`
- `data_class_not_allowed`
- `runtime_output_invalid`
- `checkpoint_integrity_failed`

## Idempotency and concurrency

The server stores the result of a successful write by workspace and idempotency key. Reuse with a different payload is rejected. `If-Match` prevents silent overwrite. Long executions pin an input revision; their results become stale proposals if the session advances.

## Event stream

Execution events: `queued`, `started`, `progress`, `tool_approval_requested`, `tool_started`, `tool_completed`, `proposal_ready`, `failed`, and `cancelled`. Progress events contain no hidden chain-of-thought.

## Compatibility

- Additive fields are backward compatible.
- Enum additions require tolerant readers or a minor contract version note.
- Breaking changes require a new major schema path and migration.
- Clients send the schema versions they understand; servers reject incompatible writes explicitly.
