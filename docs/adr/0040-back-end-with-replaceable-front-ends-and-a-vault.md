# ADR-0040: FrameShift is a back end with replaceable front ends; a front end reads the vault and writes through commands; the vault is Markdown and JSON Canvas under git

- Status: accepted
- Date: 2026-11-11
- Deciders: repository owner, through the design grilling of 2026-11-11 on the source-page vision, recorded in [#302](https://github.com/tinix84/frameshift/issues/302)
- Supersedes: none; builds on ADR-0003, ADR-0004, ADR-0013, ADR-0022, ADR-0031, ADR-0034 and ADR-0037

## Context

The manual GUI is one page laid out on the nine story-map columns. It shows
every object type at once and has a form for each command. The owner finds
it too complex to work in.

The owner built a separate canvas editor and compared it with existing
tools. Several of them already give nested canvases, Markdown notes, typed
relationships and views of claims and evidence, and they are more advanced
than a new editor would be for a long time. Two of them are plugins for
Obsidian and can run in one vault. The comparison was made from
documentation. No tool was installed or measured.

What no existing tool has is what FrameShift decides: who stands behind a
claim, which acts belong to the person, what a reasoner can do, and when a
session is finished. Those rules live in the event log (ADR-0004,
ADR-0013), not in a drawing surface.

A file that any tool can edit proves nothing about who edited it. The
author field of a commit is a configuration value that any local agent can
set.

## Decision

**FrameShift is the back end.** It owns the event log, the gates, the
provenance rules and the commands. It names no front end as its own.

**A front end reads the vault and writes through commands.** Any tool that
opens the vault's files can show a session. A change to session content is
a command to the JSON routes of the GUI boundary (ADR-0022), with the
expected revision. The token, the host check and the operator attestation
of ADR-0022 apply to every client of those routes.

**The vault is a projection.** FrameShift writes a session into a folder
as Markdown notes and JSON Canvas 1.0 files, in a git repository, with one
commit for each write. Notes link to each other with ordinary wikilinks.
The vault can be built again from the log, except for layout.

**The vault uses a short vocabulary.** Three card kinds: claim, evidence,
question. Four edge kinds: supports, contradicts, leads to, related. Each
maps onto the canonical node and edge types, which stay as they are. Card
color is the grounding band (ADR-0031). Each deep dive (ADR-0037) has its
own canvas, and a node can appear on several canvases.

**Layout is not session state.** Card positions live only in the canvas
files. Moving a card records no event and changes no revision.

**The vault has an inbox.** A file that the person puts in the inbox
folder enters as a source document or a note when the person's command
takes it in.

**Outside edits come back through the person.** An edit made to the vault
by another tool shows as a difference against the last commit that
FrameShift wrote. Layout and note text are read back as they are. Every
other difference is shown to the person, and each one that the person
accepts becomes an ordinary command. A commit is never a command, whatever
its author field says. An outside edit never changes a status, an approval
or a provenance kind.

**The first clients are two.** A command-line client gives one command for
each act of the person. A minimal Obsidian plugin does one thing: the
person selects text, picks a highlight intent, and the plugin sends the
command. Neither holds logic. The back end checks every command.

**No visual front end is chosen yet.** The owner compares candidates on
one real problem, all reading the same vault, and decides after that.

**The current page is the approval console.** Gates and confirmations stay
on it. It gets no new feature. Moving approvals to another client is a
later decision, because that path is the security boundary of ADR-0022 and
ADR-0034.

## Consequences

FrameShift does not maintain a canvas editor. The person works in tools
that others maintain, and a better tool can replace one without a change
to a session.

The rules that make a session auditable do not move. A front end that
breaks, or that writes something wrong into the vault, cannot change the
log.

A person needs more than one tool to go from first page to a signed
ending: a vault viewer, the highlight plugin or the command line, and the
approval console.

The vault can be out of step with the log between a command and the next
write. The log wins.

A local agent with a shell can run the command-line client. It rests on
the same operator attestation as the GUI: an assertion about the
configuration, not a check by FrameShift.

A viewer can drop fields that it does not know when it saves a canvas. A
field that the vault needs to find a node again must survive that, or the
read-back cannot match the card.

The vault does not follow the conventions of any one plugin. A plugin that
expects its own identifiers or its own relation file does not recognize
the vault's notes as its nodes. An export for such a plugin is possible
later. Writing a file that a plugin owns and does not document is not part
of this decision.

The owner's canvas editor is not a dependency of FrameShift.

## Alternatives considered

- **One front end of FrameShift's own, built on the owner's canvas
  editor.** It gives full control of the surface. But existing tools are
  ahead of it, and every feature would be built and maintained twice.
- **Keep the current page as the workspace.** It is the least work. But
  the owner's objection is to the page itself.
- **Fork one existing tool.** It starts from a mature surface. But it ties
  FrameShift to one project's code, and the value of FrameShift is not in
  the surface.
- **The vault files as the canonical state.** It is the simplest picture.
  But it discards the append-only log, the gates and the provenance rules.
- **A commit under the person's name counts as the person's command.** It
  makes the vault fully editable. But a reasoner could approve its own
  proposal by committing as the person, which ADR-0034 exists to prevent.
- **A canvas format that belongs to one plugin.** It gives that plugin's
  views at once. But JSON Canvas has a published specification and several
  tools read it.
- **Reduce the canonical node and edge types to the short vocabulary.** It
  removes the mapping. But it breaks the corpus fixtures and ADR-0003 to
  fix a display problem.

## Validation

[#299](https://github.com/tinix84/frameshift/issues/299) owns the
implementation and its evidence for this milestone: a session is written
as a vault that opens in Obsidian with no plugin; moving a card changes a
file and no revision; the vault holds no approval that the log does not
hold; a stale command from either client gets a revision conflict; the
study journey of #302 runs as a script of command-line calls; and the
current page gets no new feature. The read-back of outside edits is
decided here and built later. This ADR records the decision, not a
completed runtime test.
