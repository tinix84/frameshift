# Security and privacy considerations

## Assets

Problem statements, engineering IP, evidence, decisions, credentials, tool authorizations, membership, audit logs, and model/provider metadata.

## Trust boundaries

- Human browser or agent interface ↔ FrameShift API.
- Orchestrator ↔ model/runtime provider.
- Capability broker ↔ external tools and data sources.
- Application ↔ persistence and telemetry systems.
- Tenant/workspace ↔ other tenants and public exports.

## Threats and controls

| Threat | Required controls |
|---|---|
| Prompt injection in evidence/tool output | Treat as data, delimit sources, strip active content, deny authority transfer |
| Excessive tool action | Capability allowlist, scoped credentials, input schema, dry-run/approval, idempotency |
| Cross-tenant access | Tenant-scoped authorization on every read/write, isolated keys/indexes, negative tests |
| Secret or IP leakage to providers | Redaction, provider policy, data-class routing, no-training configuration where available |
| Hallucinated evidence | Provenance required; unsupported content marked inference/assumption |
| Approval spoofing | Authenticated actor, explicit action, target digest, optimistic revision, immutable event |
| State tampering | Content digests, append-only audit events, encrypted storage, integrity verification |
| Unbounded retention | Workspace policy, expiry jobs, deletion verification, derived-data tracking |
| Unsafe export | Sensitivity review, redaction preview, watermark/classification, access-controlled links |
| Dependency compromise | Locking, provenance/SBOM, automated scanning, minimal dependencies |

## Privacy principles

- Data minimization and purpose limitation.
- Explicit disclosure of selected model/provider and tool destination.
- Separate content telemetry from operational telemetry; default content logging off.
- Support data access, export, correction, retention, and deletion workflows.
- Do not infer or persist sensitive personal attributes unless essential, consented, and lawful.
- Use synthetic or irreversibly redacted evaluation data.

## Authorization model

Suggested roles are `viewer`, `contributor`, `facilitator`, `approver`, and `workspace_admin`. Domain approvals additionally require phase-specific authority. Model output never has a human role. Tool grants specify capability, resource scope, allowed operations, expiry, and whether each call requires approval.

## High-impact contexts

FrameShift is decision support, not a certified safety system. Medical, legal, financial, employment, critical-infrastructure, and safety-critical engineering uses require domain-specific governance, qualified review, and independent validation. The generic system must surface this limitation.

## Logging

Log structured event type, actor reference, revision, adapter/model identifiers, tool name, policy outcome, latency, and error code. Exclude raw secrets, full evidence bodies, hidden reasoning, and unnecessary personal data. Protect logs with access control, integrity monitoring, and retention limits.

## Security validation

Include injection fixtures, confused-deputy tests, authorization matrix tests, cross-tenant negative tests, malicious schema payloads, replay/idempotency tests, deletion verification, dependency scanning, and tabletop incident exercises before collaborative alpha.
