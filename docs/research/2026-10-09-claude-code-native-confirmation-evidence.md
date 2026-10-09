# Actual-client evidence for the native confirmation dialog: Claude Code 2.1.295

Evidence for issue [#205](https://github.com/tinix84/frameshift/issues/205), recorded against the real
client rather than a stub. The rules being exercised are owned by ADR-0014, ADR-0022 and
`frameshift/broker/confirmation.py`; this note records what was observed, not what is required.

**Date:** 2026-10-09. **Client:** Claude Code `2.1.295` (`claude --version`), Linux, run headless
with `-p` (`--print`), which the configuration policy does not allow. **Server:** `python -m frameshift.bootstrap confirmation` from this commit, with
`evals/fixtures/approval/gates.session.json` and `evals/fixtures/confirmation/frame-transition.json`
(gate `frame_selection`, target `frame_001`, session revision 7). Every exchange was captured by a
relay that logs the stdio JSON-RPC in both directions without changing it.

## Configuration identity

The validated case used a profile pinned to `claude-code` / `2.1.295` with config digest
`sha256:ebd280f31e0b9b5c71ec93b36eca01165bbe8c7439e662531635cdfb8c336dd0`. That digest covers
the configuration below, whose `--mcp-config` path pointed at a scratch directory outside the
repository:

```json
{
  "client_id": "claude-code",
  "client_version": "2.1.295",
  "launch_flags": ["--restricted", "--strict-mcp-config", "--mcp-config=<scratch>/v.mcp.json", "--tools="],
  "approval_relevant_managed_configuration": []
}
```

This profile and attestation were written by an agent for a test that can only refuse. They are
not an operator attestation, and they approved nothing.

**The attested launch was not the launch that ran.** Every run added `-p`, which the allowlist
excludes. The runs therefore show how the client behaves and which configurations the policy
refuses. They do not show the allowed launch working end to end. Only an operator at an
interactive client can show that (see the last section). An attempt to drive the interactive
client from an agent terminal was refused by the sandbox, as it should be.

## What the client declares

Before `initialize`, `2.1.295` sends `server/discover` (protocol `2026-07-28`). The server answers
`-32601`, and the client falls back to `initialize` (protocol `2025-11-25`) with:

```json
{"clientInfo": {"name": "claude-code", "version": "2.1.295"},
 "capabilities": {"roots": {"listChanged": true}, "elicitation": {"form": {}, "url": {}}}}
```

The client numbers its own requests from 0. Its `tools/list` was id 1, the same id as the server's
first `elicitation/create`. A client request that reuses the pending id is no longer taken as the
dialog's answer.

## Matrix

| # | Case | Launch | Observed | Outcome |
|---|---|---|---|---|
| 1 | Profile pinned to another version (`2.1.265`) | `-p --restricted --strict-mcp-config --tools=` | no dialog; `unsupported_configuration`, "live MCP client identity does not match the attested approval profile" | pending, no events |
| 2 | Validated `2.1.295` profile, no human present | same as 1 | one `elicitation/create` carrying the request id and digest, session and revision, gate, target and target digest, actor authority, permitted dispositions and the exact proposal; the client answered `{"action": "cancel"}` | pending (`approval_required`, "confirmation was cancelled"), no events |
| 3 | Project-settings `Elicitation` hook that accepts with `approved` | `-p --strict-mcp-config --tools=` (no `--restricted`) | the hook answered `{"action": "accept", "content": {"disposition": "approved"}}` | approval without a human: the reason `--restricted` is required |
| 4 | Same project hook | same as 1 | the hook was ignored; the client cancelled | pending |
| 5 | Same hook passed as `--settings <file>` | same as 1, plus `--settings <file>` | the hook still ran and accepted. Under the earlier policy, which only required flags to be present, the server committed an approval of `frame_001` as `user_lead_eng` with no human. | now refused before any dialog: `unsupported_configuration` |

Each run also passed `--mcp-config` and pre-approved the one MCP tool with `--allowedTools`. Case 5 is why the launch is now an exact allowlist (`--restricted`, `--strict-mcp-config`,
`--tools=`, one `--mcp-config=`), and why the configuration must state an empty
`approval_relevant_managed_configuration`.

## Not demonstrated here

- **Managed settings.** `claude --help` says managed settings still apply under `--restricted`.
  A managed `Elicitation` hook was not tested, because the sandbox refused the write to
  `/etc/claude-code/`. It stays something the operator attests to.
- **Launch flags are attested, not observed.** The server sees the configuration file, not the
  process's arguments. An operator who launches with flags other than the ones attested defeats
  the check.
- **The allowed launch itself.** Cases 2 and 4 show that a headless client (`-p`) with no human
  present cannot accept. They do not show the dialog rendering, a person accepting it, or
  edit-then-review under the exact allowed launch. Those need the operator at an interactive
  `claude` with the pinned configuration. An agent must not supply those answers.
  Steps for the operator:
  1. Pin a profile, configuration and attestation for the installed version, outside the
     repository.
  2. Launch `claude --restricted --strict-mcp-config --mcp-config=<file> --tools=`.
  3. Ask it to call `frameshift_confirm` with the pending request id.
  4. Answer the dialog three times: `approved`; `edited` with a changed proposal, then a second
     dialog; and `rejected`.
  5. Record each tool result next to this note.
