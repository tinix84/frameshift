# ADR-0015: Enforce module boundaries around orchestration

- Status: accepted
- Date: 2026-09-06
- Deciders: repository owner, through the module-boundary grilling session
- Supersedes: ADR-0013 in part, its deferral of atomic commits and concurrent-writer handling; its event format and replay rules stand

## Context

ADR-0008 chooses a modular monolith but leaves its import boundaries unnamed.
ADR-0009 makes FrameShift an inbound MCP server with provider-neutral contracts.
The owner resolved the concrete boundaries in [What module names and dependency
rules should an architecture test enforce?](https://github.com/tinix84/frameshift/issues/35).
The purpose is to keep policy and state changes consistent across entry points,
while allowing protocol, validation, and storage implementations to change.

## Decision

All names below are under `frameshift`. The table permits direct imports;
unlisted cross-module imports are forbidden. Imports within a module are allowed,
subject to the narrower boundaries below.

| Module | May import |
|---|---|
| `contracts` | No other application module |
| `canonical` | `contracts` |
| `validation` | `contracts`, `canonical` |
| `broker` | `contracts`, `canonical`, `validation` |
| `export` | `contracts`, `canonical` |
| `orchestration` | `contracts`, `canonical`, `validation`, `broker`, `export` |
| `persistence` | `contracts`, `canonical`, `validation`, `orchestration.ports` |
| `mcp` | `contracts`, `orchestration.api` |
| `bootstrap` | All modules, solely to assemble the application |

`orchestration` is the sole coordinator of session changes and application reads.
It checks workflow phase and revision, obtains broker authorization and
validation results, and commits through its persistence interface. MCP handlers
and proposal-processing code cannot write directly to storage. Reads, history,
and checkpoint queries also pass through orchestration and access policy.

`orchestration.api` exposes provider-neutral application operations.
`orchestration.ports` contains interfaces only and may import only `contracts`
among application modules. Orchestration owns the persistence interface;
`persistence` implements it. Package initializers cannot re-export implementations
in a way that introduces forbidden dependencies or a cycle through these ports.

The persistence commit operation checks the expected revision against the stored
revision and makes a state transition and its events visible atomically. Two
requests based on the same revision cannot both commit; a conflict returns to
orchestration. This is a logical commit guarantee, not a requirement to maintain
two independent authoritative records: ADR-0013's log remains authoritative and
snapshots remain derived. The JSONL format is retained; implementation must earn
the stronger guarantee rather than assume that a file append provides it.

The broker owns capability authorization, policy and approval binding;
orchestration owns workflow progression. Both checks must pass before an
operation executes. Broker output does not itself commit session state.

Validation operates on explicitly supplied data and rules. It cannot read
session storage, call tools, or change state. `validation.schema` alone imports
the third-party JSON Schema validator, translating its output and exceptions
into ordinary results with field paths and stable error codes.

`canonical` owns canonical encoding and digest calculation independently of
storage. Startup supplies schema-derived rules. `contracts` owns shared error
codes and provider-neutral result types, not workflow behavior. Canonical JSON
and the published schemas remain authoritative; Python types confer no new
wire-level requirements.

`export` renders supplied data; orchestration obtains and authorizes that data.
Only `mcp` imports the MCP SDK and translates protocol requests and confirmation
responses. SDK objects never cross into application operations. The established
human-confirmation decision remains binding; protocol translation grants no
authority by itself.

`bootstrap` connects the concrete implementations and supplies static contract
resources. No application module imports it. It contains no approval or workflow
rules. Reasoning engines remain prompt contracts under ADR-0009; this layout
does not introduce outbound model calls or a runtime dependency on the legacy
provider adapters.

## Enforcement and consequences

Import checks enforce the direct table and forbidden transitive paths. In
particular, validation and the broker cannot reach persistence or orchestration;
orchestration and MCP cannot reach concrete persistence; persistence can reach
only orchestration's interface-only ports; and nothing can reach bootstrap by
import. Legitimate transitive calls through the application API remain allowed:
MCP can reach broker checks through orchestration without importing the broker.

Dynamic imports cannot bypass the boundaries. Static import checks establish
structure, not correct behavior of injected objects, human approval, or policy.
Those guarantees require behavioral evidence in addition to architecture checks.
The pinned import-linter selected in ADR-0009 enforces the import graph; any
coverage gaps must be handled explicitly rather than called a passed guarantee.

Existing broker imports of persistence hashing and orchestration error codes
must be disentangled. Existing resource-loading helpers need separation from
checks on supplied data. The decision accepts explicit interfaces and query
methods in exchange for keeping these dependencies visible. It neither claims
that the present code conforms nor performs that refactor.

## Alternatives considered

- Direct persistence access from MCP handlers: fewer forwarding methods, but
  duplicates policy and workflow entry points.
- Orchestration imports concrete storage: simpler assembly, but couples workflow
  rules to storage and undermines replacement behind a stable interface.
- Leave canonical hashing under persistence and errors under orchestration:
  convenient reuse, but pulls forbidden dependencies into the broker.
- Check direct imports only: misses a forbidden dependency routed through a
  helper. Import checks alone also cannot establish authorization correctness.

## Validation

[Expose revision-bound domain commands through the MCP boundary](https://github.com/tinix84/frameshift/issues/172)
owns implementation and conformance evidence for this architecture: enforceable
import rules with negative examples, production dependency closure, behavioral
policy and approval checks, atomic revision conflicts, and interrupted commits
that cannot restore a partially committed transition. This decision resolves
the architecture question; it does not complete the implementation or its tests.
