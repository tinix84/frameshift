# ADR-0034: A tandem run approves under its own profile, and a local profile refuses approval while a reasoner is attached

- Status: accepted
- Date: 2026-11-05
- Deciders: repository owner, through the design decision on [#291](https://github.com/tinix84/frameshift/issues/291)
- Supersedes: none; extends ADR-0022 with a third manual-GUI approval profile and a refusal rule for the local profile

## Context

ADR-0022 rests manual-GUI approvals on the operator's attestation that no agent
or model runs under their account while the GUI is open. The local profile pins
that text in its configuration digest.

A tandem run ([#286](https://github.com/tinix84/frameshift/issues/286)) is the
manual GUI plus a reasoner, such as Claude Code, that drives
`python -m frameshift.bootstrap reasoner` on the same store. The reasoner server
exposes no approval tool. But the reasoner runs under the operator's account
and can reach the loopback page through its other tools. A tandem run thus
makes the local attestation false.

An approval made in a tandem run still records the local manual profile. The
log then names a trust boundary that did not hold, and nothing in it shows that
an agent was running. ADR-0023 met the same kind of problem for hosted runs: a
different trust boundary got its own profile.

## Decision

**A tandem run is its own approval profile.** The operator starts the GUI with
`--tandem` for a tandem run. `bootstrap` then builds a profile distinct from the
local and the hosted profiles. Its pinned configuration contains the tandem
attestation: an agent may run under the operator's account while the server is
open, and the operator alone answers the confirmations on this page. The server
prints that text at start and the page states it.

**Tandem approvals advance gates.** Every existing guard still decides: the
confirmation broker binds the response to the request digest, target digest,
revision and actor authority, and `transitions.attempt` applies sequence then
binding. Each tandem approval records the tandem `profile_id`. A tandem
approval is never evidence for ADR-0014's native-dialog guarantee
([#205](https://github.com/tinix84/frameshift/issues/205)) or for any other
claim of a trusted human confirmation.

**A reasoner server marks the store it is attached to.** While it runs, the
reasoner server leaves a presence marker in its store and removes the marker
when it stops. No reasoner tool reads, writes or removes the marker.

**A local profile refuses approval while the marker is present.** Before each
confirmation, a GUI under the local profile checks the marker. If the marker is
present, the GUI refuses the approval with a published error code and appends
nothing. The check runs at each confirmation, so a reasoner that starts after
the GUI still blocks local approvals. A marker that a crashed reasoner left
keeps local approvals refused until the operator clears it or restarts the GUI
under `--tandem`. Proposals, answers, concessions, parking and reopening are not
approvals, and the marker does not block them.

A tandem GUI approves whether or not the marker is present. This ADR does not
change hosted runs, and `--tandem` together with `--hosted` refuses to start.

## Consequences

Every approval names the trust boundary that bound it: local, hosted or tandem.
A reader of the log can separate tandem approvals from solo approvals, and
evidence work can exclude them.

If the operator forgets `--tandem`, the run fails closed: the GUI refuses each
approval and tells the operator why. Without the marker, the same mistake
records the local profile, as today.

The marker stops an accident, not a hostile agent. An agent under the
operator's account can delete the marker, start the GUI itself, or answer a
confirmation on the page. The tandem attestation that the operator alone
answers is the operator's claim only, and it is weaker than the local
attestation. FrameShift does not verify it, as ADR-0022 and ADR-0014 also do
not verify theirs.

The tandem profile is one more pinned configuration. A change to its
attestation text is a change of profile and suspends approvals, as ADR-0014
requires.

This ADR does not decide whether tandem sessions count as input for engine
evaluation. Their logs name the reasoner as a `runtime` actor, so a later
decision can select them.

## Alternatives considered

- **A tandem profile only, with no marker**: gives the same log meaning when the
  operator selects `--tandem`. But a forgotten flag silently records the local
  profile, which is the problem this ADR solves.
- **No gate approvals while a reasoner is attached**: keeps the local
  attestation true for every approval. But a tandem session can pass no gate
  until the operator stops the reasoner, so intake and frame selection break
  the tandem loop that #286 builds.
- **Keep ADR-0022 unchanged and document the limit only**: costs no code. But
  the log keeps naming a trust boundary that did not hold, and tandem and solo
  approvals cannot be told apart afterwards.
- **Detect the reasoner from the process table instead of a marker**: depends on
  the operating system and on process names, and an agent can rename a process
  as easily as it can delete a file.

## Validation

[#291](https://github.com/tinix84/frameshift/issues/291) owns the
implementation and its evidence: a distinct tandem profile whose digest
includes the tandem attestation; tandem approvals that record that profile and
pass every existing guard; a marker present while the reasoner runs and gone
after a clean stop; local-profile approvals refused at each confirmation while
the marker is present, with a published error code and an unchanged log; a
stale marker that keeps local approvals refused; `--tandem` with `--hosted`
refused at start; and an unchanged reasoner tool list. This ADR records the
decision, not a completed runtime test.
