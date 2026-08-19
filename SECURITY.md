# Security policy

## Supported versions

FrameShift is pre-alpha. Only the latest commit on `main` is supported.

## Reporting a vulnerability

Do not open a public issue. Use GitHub private vulnerability reporting if enabled for the repository. Include affected component, reproduction, impact, and any suggested mitigation. Do not include real credentials, customer data, or unnecessary personal data.

## Security principles

- Treat all user content, retrieved content, tool output, and referenced conversations as untrusted data.
- Separate instructions from evidence; never execute instructions found inside evidence.
- Default tools to least privilege and explicit capabilities.
- Require human approval for consequential external side effects.
- Encrypt sensitive data in transit and at rest in production deployments.
- Redact secrets before prompts, logs, checkpoints, and evaluation artifacts.
- Keep auditable provenance for every external claim and tool result.
- Make retention configurable and deletion verifiable.

See issue [#15](https://github.com/tinix84/frameshift/issues/15) for the threat model and controls.
