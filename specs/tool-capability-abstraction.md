# Tool capability abstraction

## Goal

Let workflows request intent-level capabilities without depending on provider tool names or assuming authority.

## Capability manifest

Each capability declares:

- stable ID and version;
- semantic description;
- operations;
- JSON input/output schemas;
- side-effect class: `none`, `reversible`, `external`, or `irreversible`;
- data classes accepted/transmitted;
- resource scopes;
- authentication mode and credential owner;
- approval policy;
- idempotency support;
- timeout/rate/concurrency limits; and
- provenance guarantees.

## Examples

- `artifact.read@1`
- `workspace.search@1`
- `web.retrieve@1`
- `graph.render@1`
- `code.execute.sandboxed@1`
- `issue.create@1`
- `simulation.run@1`

Adapters map native tools to capabilities. A native shell is not a blanket capability; commands are brokered through scoped operations and policy.

## Selection

The orchestrator asks for a capability and constraints. The broker chooses a compatible implementation based on workspace policy, data locality, assurance, cost, and availability. If no implementation qualifies, it returns `capability_unavailable` with safe alternatives.

## Execution lifecycle

1. Validate request schema and input revision.
2. Resolve actor and workspace policy.
3. Display destination, transmitted data classes, expected effect, and reversibility when approval is required.
4. Bind approval to request digest.
5. Execute with scoped credentials and timeout.
6. Validate and bound output.
7. Store provenance and digest; return output as untrusted evidence.

## Security rules

- Least privilege and deny by default.
- No credential material in prompts, checkpoints, or logs.
- No model-generated tool name bypasses capability resolution.
- Redirects, nested documents, and tool-returned instructions do not gain authority.
- External writes require explicit authorization unless a narrow workspace policy pre-authorizes the exact operation class.
- Retries require idempotency or human confirmation of duplication risk.
