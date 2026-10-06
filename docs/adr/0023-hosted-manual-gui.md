# ADR-0023: Serve the manual GUI to one operator over the network

- Status: accepted
- Date: 2026-10-06
- Deciders: repository owner, on review of [#235](https://github.com/tinix84/frameshift/pull/235)
- Supersedes: none; extends ADR-0022, whose loopback-only rule it relaxes for `--hosted` runs

## Context

ADR-0022 lets one operator walk a session through a loopback page. The same
operator wants to do it from a phone or another machine, which needs the server
on a container platform behind TLS. That is a different trust boundary from
ADR-0022's: the approval endpoint becomes reachable from the internet, and the
question changes from "does an agent run under my account" to "who holds the
credential".

## Decision

`--hosted` changes three things and nothing about the approval guards:

- the server listens on all interfaces behind the platform's TLS proxy and
  answers only for the configured public host name;
- every request, the page included, must carry HTTP Basic credentials matching
  a deployment password of at least sixteen characters; the server refuses to
  start without one, and refuses any non-loopback bind without both a password
  and a host name;
- the launch token remains as the cross-site defence, because a browser resends
  Basic credentials on a cross-site request by itself but cannot add the
  token's custom header without a preflight.

A hosted run is its own approval profile, distinct from ADR-0022's local one,
and its attested configuration digest includes the bind address, the public
host names and the authentication scheme, so changing any of them is a change
of profile. The operator attestation then means "whoever holds the deployment
password". Event logs live on a persistent volume, never on the container's own
filesystem.

## Consequences

The trust boundary moves from "this account" to "this password". A leaked
password grants the operator's full approval authority until it is rotated, and
the log will attribute what its holder approved to the configured operator.

The server enforces the password's length, not its randomness, and does not
rate-limit failed attempts. A long random password and the platform's access
controls carry that risk; rate limiting is the first hardening to add if the
deployment is shared beyond one operator.

An agent without the password cannot approve, so a hosted run is stronger than
a local one against an agent on the operator's machine, as long as the password
is not stored where that agent can read it.

## Alternatives considered

- **Keep hosted mode inside ADR-0022**: the first draft did. It bundled an
  internet-facing endpoint under a decision about a local page, so a reader
  accepting one accepted the other.
- **A platform that scales to zero with a read-only filesystem**: incompatible
  with the append-only log (ADR-0013) and with pending confirmations held in
  memory.
- **Open access with no password**: every visitor would approve as the one
  configured operator, into a log that cannot be edited.

## Validation

`frameshift/tests/test_gui.py` (`HostedMode`): requests without the password are
refused, the password alone does not open the API, only the public host is
served, and a network bind without a password will not start; a hosted launch
refuses a short password or a missing host name.
`frameshift/tests/test_sessions.py`: hosted and local runs are distinct
approval profiles.
