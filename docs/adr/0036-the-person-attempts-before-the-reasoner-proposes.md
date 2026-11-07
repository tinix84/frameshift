# ADR-0036: The person attempts before the reasoner proposes; the order is derived from the log, and a returning person sees their own trail first

- Status: accepted
- Date: 2026-11-07
- Deciders: repository owner, through the design grilling of 2026-11-06 on the companion vision, which feeds [#195](https://github.com/tinix84/frameshift/issues/195) and [#188](https://github.com/tinix84/frameshift/issues/188)
- Supersedes: none; builds on ADR-0028, ADR-0031, ADR-0032, ADR-0034 and ADR-0035

## Context

A reasoner's first fluent answer anchors the person. After the person reads
it, their own frame or cause tends to become a variant of it. ADR-0011 and
ADR-0024 keep several candidates, but all of them can come from the
reasoner.

In a tandem run (ADR-0034) the reasoner writes its proposals to the shared
event log, with a `runtime` actor. The person also reads the reasoner's text
in the reasoner's own chat. So the GUI cannot hide a proposal from the
person. What the log can prove is order: whether the person's `observed`
attempt has a lower sequence number than the reasoner's first proposal for
the same step.

Not every column needs the person's attempt. A reasoner's breadth helps when
it looks for evidence or generates options, and ADR-0011 already keeps the
person's original idea as an option. Slowness pays where the person decides
what the problem is, why it happens, what matters, and what to sign.

A person who works on several problems returns to a session after days. A
summary written by a reasoner feels like understanding, but it is the
reasoner's reading of the person's work.

## Decision

**Four columns are slow.** In the story-map columns `column:reframe`,
`column:causes`, `column:compare` (for criteria only) and `column:decide`,
the person's own attempt comes first. The other columns may go at the
reasoner's pace.

**An own attempt is an `observed` statement.** The person records it through
their boundary (ADR-0028), before the reasoner's first proposal for the same
step. No new event type exists, and no flag is recorded.

**The order is derived from the log.** A read-only function compares the
sequence of the person's `observed` statements with the sequence of the first
proposal from a `runtime` actor for the same step. The result is **own attempt
first** or **skipped attempt**. A skipped attempt is not an error, and no gate
reads it. [#195](https://github.com/tinix84/frameshift/issues/195) decides the
rule that matches an attempt to a step.

**The own-attempt rate is an indicator.** It is the share of slow-column
steps with an own attempt first. It shows the person how they worked. It is
never a target and never gates. A target would turn the attempt into filler
text.

**The GUI collapses early proposals.** In a slow column, the GUI collapses
reasoner proposals made before any own attempt behind an action that shows
them. The action writes nothing to the log. The collapse is an aid, not
evidence.

**A returning person sees their own trail first.** When the person opens a
session, the GUI shows the re-entry trail: the person's `observed`
statements, the working frame with its selection rationale (ADR-0035), open
challenges (ADR-0031), and parked lines with their reasons (ADR-0032).
Reasoner content is one action away. No reasoner-written summary replaces the
trail.

**The companion modes are a closed set of four.**

| Mode | Where it is decided |
|---|---|
| Own attempt before the reasoner proposes | this ADR |
| Explain-back at the two hard gates | ADR-0035 |
| Challenge: the person questions the reasoner's claim | ADR-0031 |
| Re-entry from the person's own trail | this ADR |

Spaced revisits of parked lines and explain-back outside the two hard gates
are deferred, not rejected. Spaced revisits need a model of time, which
ADR-0032 left open.

## Consequences

The log shows, step by step, whether the person thought first or read first.
The proof costs no new event type and no reducer change.

The person can still read the reasoner first. The system does not stop
them. It shows the order afterwards, to the person and to anyone who reads
the log.

The derivation depends on a step-matching rule that #195 owns. Until #195
decides it, the derivation cannot be built.

The re-entry trail makes the person's own words the way back into a
session. A session with few `observed` statements has a thin trail, and the
person sees that.

## Alternatives considered

- **Hide proposals until the person reveals them, and log the reveal.** It
  adds an event type. But in a tandem run the person reads the reasoner's
  text in its own chat, so a GUI reveal proves nothing about anchoring.
- **Block the reasoner until the person attempts.** It takes the tandem
  run's pace away and needs a reasoner-side rule that FrameShift cannot
  enforce (ADR-0009).
- **Make every column slow.** It wastes the reasoner's breadth where breadth
  helps, in evidence and options.
- **A reasoner-written summary on re-entry.** It is fast to read. But it
  replaces the person's reasoning with the reasoner's reading of it.
- **Name no companion modes, only mechanisms.** #195 asks for a minimum
  taxonomy, and without names the modes drift.

## Validation

[#294](https://github.com/tinix84/frameshift/issues/294) owns the
implementation and its evidence: the derivation gives "own attempt first"
and "skipped attempt" on a history fixture with one of each; the derivation
writes nothing, and both reducers are unchanged; no gate reads the
own-attempt rate; the GUI collapse writes nothing to the log; and the GUI
opens a session on the re-entry trail. This ADR records the decision, not a
completed runtime test.
