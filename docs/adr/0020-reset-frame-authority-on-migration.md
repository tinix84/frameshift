# ADR-0020: Reset frame authority when migrating axes

- Status: accepted
- Date: 2026-09-09
- Deciders: repository owner, through the implementation continuation for #86
- Supersedes: ADR-0018 and ADR-0019 in part, their deferral of migration disposition

## Context

ADR-0019 creates a linked version-2 session and checkpoint while preserving the
version-1 source. It deliberately left the status of converted frames and the
treatment of historical approvals for owner direction. The owner selected the
recommended disposition during implementation of #86: converted frames return
as proposals and version-1 approval records are not copied.

Adding `system_boundary` changes the content digest even where both new axes can
be recovered without ambiguity. An approval bound to the legacy content and
revision cannot authorize that changed frame in the new session.

## Decision

Every converted frame has status `proposed` and a digest over its version-2
content. The linked session has no active frame and copies no approval records.
It begins at revision zero in the framing phase, with event cursor zero, so a
new frame-selection confirmation is required before reasoning advances.

Legacy `component`, `subsystem`, and `product` values map to the same value on
both axes. Legacy `business` maps to abstraction level `business` and system
boundary `business_model`. Values that name only a ladder rung or only a
boundary do not supply the missing axis: conversion returns a typed pending
human-review result and creates no checkpoint.

The new session carries no pending proposals or execution summaries from the
source revision. The immutable source checkpoint remains the inspectable record
of those items. The caller supplies exact prompt identities for the new
session; migration does not silently promote a currently installed prompt.

## Consequences

Migration preserves content and lineage without transferring authority. Even
an unambiguous structural conversion requires a fresh human frame selection,
and a legacy approval is observably stale against the new frame digest.

A lateral value such as `supply_chain` cannot be guessed into a ranked
abstraction. Completing such a conversion needs a separately trusted human
choice for both axes.

## Alternatives considered

- Copy historical approvals: rejected because their target digest and revision
  bind different content in a different session.
- Preserve `working` status without an approval: rejected because status would
  imply authority the new session does not contain.
- Carry legacy pending proposals into revision zero: rejected because they were
  produced against the source schema and revision; the source retains them.

## Validation

#86 owns a source-preserving migration fixture and public-operation tests for
new identities, v2 schema and digest validity, reset history and authority,
ambiguous-axis review, corrupt-source refusal, and unsupported-version refusal.
