# ADR-0037: Source documents and highlights are session objects; a highlight carries one intent from a closed set and is the request to a reasoner

- Status: accepted
- Date: 2026-11-11
- Deciders: repository owner, through the design grilling of 2026-11-11 on the source-page vision, recorded in [#302](https://github.com/tinix84/frameshift/issues/302)
- Supersedes: none; builds on ADR-0012, ADR-0026, ADR-0028, ADR-0031 and ADR-0034

## Context

A session starts today from statements that the person types. Much of what a
person wants to understand arrives as a text by someone else: a transcript,
an article, a failure report. That text has no place in a session. The
person cannot keep it in view, and cannot point at the part of it that is
too coarse.

ADR-0028 lets only the person's boundary record an `observed` statement. A
transcript is not what the person observed. If it entered as an intake
record, every claim in it would count as the person's own observation.

In a tandem run (ADR-0034) work flows one way. The reasoner server has no
record of a request from the person and no tool that lists open work. The
reasoner reads the session only when the person asks it to.

## Decision

**A source document is a session object.** It is a text by an author other
than the person. The session records its id with the new `src_` prefix, its
content digest, title, author, date, tags and access policy. The text stays
outside canonical state, stored by its digest. A source document is
immutable. A new version is a new source document that supersedes the older
one.

**The person's own description stays an intake record.** A statement taken
from a source document is `sourced` and cites the `src_` id. It is never
`observed`. A session can hold many source documents, and the person can add
one at any time.

**A highlight is a session object.** It carries an id with the new `hl_`
prefix, the digest of the text it marks, a character range, the quoted
text, and one highlight intent. Only the person's boundary records a
highlight. Highlights can overlap, and one highlight carries one intent.

**The intents are a closed set of five.**

| Intent | What it asks | Of whom |
|---|---|---|
| `deep_more` | what the span rests on, one level down | a reasoner |
| `ask_for_source` | a citation for the span | a reasoner |
| `unclear_term` | a definition | a reasoner |
| `crosslink` | nothing; it joins the span to a node or a note | the person's own act |
| `disagree` | nothing; it records a contradiction | the person's own act |

Adding an intent is a superseding ADR.

**A highlight is the request.** A highlight with one of the three asking
intents is open until a proposal cites it or the person closes it. No
separate request object exists. A reasoner-facing boundary can read open
highlights and cite one. It cannot record, close or change a highlight.

**One `deep_more` goes one level.** A reasoner answers with at most seven
proposals, each with a declared provenance kind that its sources earn
(ADR-0026). Nothing is proposed below a proposal that the person has not
accepted.

**A note is the person's words.** A note on a span or a node enters as an
intake record (ADR-0028), so it can ground other nodes.

**A superseded source keeps its highlights.** When a new version supersedes
a source document, each highlight is found again by its quoted text. A
highlight that cannot be found is flagged as orphaned and stays on the old
version. It is never moved silently.

## Consequences

The first page of a session can be someone else's text without weakening
ADR-0028. The provenance kind still says who stands behind a claim.

The source text is not in the event log or in a checkpoint. A public
fixture can hold the digest, the highlights and the graph of a text that
the repository cannot redistribute. A session whose source text is lost
keeps its highlights but cannot show them in place.

A fixed intent set means that a color has the same meaning in every session
and in every export. A person who wants a sixth intent cannot have one
without a new decision.

How an attached reasoner learns that a highlight is open, without the
person switching windows, is not decided here.
[#300](https://github.com/tinix84/frameshift/issues/300) tests a waiting
tool. Until it reports, the pickup is the person asking the reasoner to
read the open highlights.

Reasoner span suggestions and pre-marking were agreed as a direction, with
ADR-0036's order. They are not part of this decision.

## Alternatives considered

- **Every first page is an intake record.** It is one path instead of two.
  But it records another author's claims as the person's observations.
- **One request object that points at a highlight.** It separates the mark
  from the ask. But every asking highlight would have exactly one request,
  so the second object carries nothing.
- **Colors that the person defines, with their own prompts.** It is
  flexible. But a color then means something different in each session, and
  the highlighter becomes a prompt launcher.
- **A deep dive that runs down to facts.** It is faster. But the person
  receives a finished tree and reviews it instead of thinking it through.
- **The source text inside canonical state.** A session is then complete in
  one place. But a checkpoint would carry texts that the person has no
  right to copy.

## Validation

[#296](https://github.com/tinix84/frameshift/issues/296) owns the
implementation and its evidence: both reducers and a history fixture know
the new events; a statement that cites a source document is refused as
`observed`; a reasoner tool lists open highlights and none records or
closes one; a highlight on a superseded source is found again or flagged as
orphaned; and the source text is absent from the event log and the
checkpoint. This ADR records the decision, not a completed runtime test.
