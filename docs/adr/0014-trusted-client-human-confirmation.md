# ADR-0014: Trusted client confirmation for human approvals

- Status: accepted
- Date: 2026-09-06
- Deciders: repository owner, through the human-confirmation grilling session
- Supersedes: none

## Context

ADR-0002 binds a human disposition to content and revision. ADR-0009 makes an
MCP client the interaction surface. Neither establishes how the server knows
that a response came from a human: a model can supply an actor field, and a
separate approval command is not independent when the agent can invoke it.

Claude Code provides native MCP elicitation dialogs, but its elicitation hooks
can answer without displaying the dialog or alter the response. The protocol
response alone therefore does not establish human presence. The owner resolved
the trust boundary in [Which mechanism establishes human confirmation in the
supported clients?](https://github.com/tinix84/frameshift/issues/174).

## Decision

The first local release trusts the client application and local operating
system to report human confirmation honestly. It protects against model-issued
calls and untrusted content within that boundary; it does not claim protection
against a compromised client or operating system.

Claude Code's native MCP elicitation dialog is the first release's only approval
interface. FrameShift supplies the exact proposal for review and binds the
response to its pending request, target digest, revision, and actor authority.
An ordinary model tool call or a model-supplied human actor field cannot grant
approval.

The operator attests a pinned, tested client version and configuration at
session start. That configuration must prevent automatic acceptance or
rewriting of FrameShift approvals, and the agent must be unable to modify it.
Hooks may veto an approval but cannot grant one or change what was approved.
A configuration change suspends further approvals until revalidation.

This attestation is the operator's assertion about the supported configuration,
not independent verification by FrameShift before each approval. An operator's
assertion is not a substitute for the implementation's conformance evidence.

An edit does not also approve the edited proposal. The revised proposal is
validated and displayed with its new digest and revision, then requires a fresh
human confirmation. Unsupported or unvalidated client configurations may
prepare proposals but cannot approve them. A separate approval CLI is deferred
until a demonstrated need and a trustworthy design justify it.

## Consequences

The supported configuration is part of the approval guarantee. Its protection
and the correspondence between a displayed proposal and the response must be
demonstrated with the actual client. A generic elicitation capability or an
`accept` response is insufficient evidence by itself.

This keeps the local release's interaction inside the existing client while
making its trust assumption explicit. It preserves provider-neutral domain
approvals; another client needs its own evidence before it can grant them.

## Alternatives considered

- Accept a human actor field in a tool call: cannot distinguish a model claim
  from a human disposition.
- Add an approval CLI immediately: another command available to the agent
  establishes no independent authority and adds an interface without resolving
  the trust boundary.
- Independently verify the whole client configuration before every approval:
  a stronger mechanism than the operator-attested boundary selected here.
- Approve while submitting edits: makes it unclear whether the human reviewed
  the final validated content.

## Validation

[Bind approvals to a trusted human confirmation](https://github.com/tinix84/frameshift/issues/169)
owns the implementation and its evidence: actual native-dialog confirmation;
model-forged approvals refused; automatic or rewritten responses disqualifying
the configuration; configuration changes suspending approval; edit-then-review;
and unsupported configurations leaving proposals pending. Existing digest,
revision, and authority guards remain binding. This ADR records the decision,
not a completed runtime test.

Sources consulted: [Claude Code elicitation hooks](https://code.claude.com/docs/en/hooks#elicitation)
and [MCP elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation).
