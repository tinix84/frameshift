"""A decision record that distinguishes fact from assumption (#23 FR-10).

FR-10's acceptance signal is not "an export exists" — it is that the export
*distinguishes facts, assumptions, inference, and approval*. A record that runs
the four together is the thing an auditor cannot use, because the question they
arrive with is always which of the four a given line is.

The distinction is already in the data and needs no engine to produce. Every
material claim carries `provenance.kind`, and the five values map onto FR-10's
four categories with one left over: `unknown` is its own heading rather than
being folded into assumption, since "nobody recorded where this came from" and
"someone assumed it" are different admissions and the second is the more
flattering of the two.

Nothing here is generated prose. Every line is a value already committed to
state, which is what makes the record auditable rather than merely readable —
and it is why the export carries no rationale beyond what a human wrote on an
approval.
"""

from __future__ import annotations

# FR-10's four, plus the honest fifth. Order is the order they are rendered in:
# what is known first, what is supposed last.
CATEGORIES = (
    ("Established", ("observed", "sourced"), "Recorded from the session or a cited source."),
    ("Inferred", ("inferred",), "Derived by the system. Traceable, not observed."),
    ("Assumed", ("assumed",), "Taken as true without evidence. The first thing to challenge."),
    ("Unattributed", ("unknown",), "Provenance was not recorded. Treat as unverified."),
)

COLLECTIONS = (
    ("statements", "text"),
    ("frames", "question"),
    ("options", "summary"),
    ("criteria", "name"),
)


def _text(item: dict, preferred: str) -> str:
    for key in (preferred, "label", "summary", "text", "question", "name", "id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return item.get("id", "(no text)")


def claims(session: dict) -> list[dict]:
    """Every material claim in canonical state, with where it came from.

    A claim is anything carrying provenance. Collecting them by that property
    rather than by collection means a new kind of object joins the record the
    moment it records where it came from, without this module learning about it.
    """
    found: list[dict] = []
    for collection, preferred in COLLECTIONS:
        for item in session.get(collection, []):
            if isinstance(item, dict) and isinstance(item.get("provenance"), dict):
                found.append(
                    {
                        "id": item.get("id"),
                        "where": collection,
                        "text": _text(item, preferred),
                        "kind": item["provenance"].get("kind", "unknown"),
                        "source_ids": list(item["provenance"].get("source_ids", [])),
                    }
                )
    graph = session.get("graph", {})
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and isinstance(node.get("provenance"), dict):
            found.append(
                {
                    "id": node.get("id"),
                    "where": f"graph node ({node.get('type', 'node')})",
                    "text": _text(node, "label"),
                    "kind": node["provenance"].get("kind", "unknown"),
                    "source_ids": list(node["provenance"].get("source_ids", [])),
                }
            )
    # An edge asserts that one thing bears on another, which is a claim like any
    # other and is often the one carrying the least evidence.
    labels = {node.get("id"): _text(node, "label") for node in graph.get("nodes", [])}
    for edge in graph.get("edges", []):
        if isinstance(edge, dict) and isinstance(edge.get("provenance"), dict):
            source = labels.get(edge.get("source"), edge.get("source"))
            target = labels.get(edge.get("target"), edge.get("target"))
            found.append(
                {
                    "id": edge.get("id"),
                    "where": f"graph edge ({edge.get('type', 'edge')})",
                    "text": f"{source} -> {target}",
                    "kind": edge["provenance"].get("kind", "unknown"),
                    "source_ids": list(edge["provenance"].get("source_ids", [])),
                }
            )
    return found


def _working_frame(session: dict) -> dict | None:
    active = session.get("active_frame_id")
    for frame in session.get("frames", []):
        if frame.get("id") == active:
            return frame
    return None


def render(session: dict) -> str:
    """The decision record, as markdown."""
    lines = [f"# Decision record: {session.get('title', session.get('id', 'untitled'))}", ""]
    lines.append(
        f"Session `{session.get('id')}` at revision {session.get('revision')}, "
        f"phase {session.get('phase')}, status {session.get('status')}."
    )
    lines.append("")

    frame = _working_frame(session)
    lines.append("## The problem being solved")
    lines.append("")
    if frame is None:
        lines.append("No working frame has been approved. Nothing here is decided.")
    else:
        lines.append(f"> {_text(frame, 'question')}")
        if frame.get("outcome"):
            lines.append("")
            lines.append(f"Outcome sought: {frame['outcome']}")
    lines.append("")

    everything = claims(session)
    for heading, kinds, note in CATEGORIES:
        selected = [item for item in everything if item["kind"] in kinds]
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(f"_{note}_")
        lines.append("")
        if not selected:
            lines.append("Nothing in this category.")
        for item in selected:
            cited = f" — from {', '.join(item['source_ids'])}" if item["source_ids"] else ""
            lines.append(f"- **{item['id']}** ({item['where']}): {item['text']}{cited}")
        lines.append("")

    lines.append("## Approvals")
    lines.append("")
    lines.append("_Who signed what, bound to the content and revision they saw._")
    lines.append("")
    approvals = session.get("approvals", [])
    if not approvals:
        lines.append("No approval has been recorded. Nothing here carries a human signature.")
    for approval in approvals:
        actor = approval.get("actor", {})
        lines.append(
            f"- **{approval.get('disposition')}** of `{approval.get('target_id')}` "
            f"by {actor.get('id')} ({actor.get('role')}) "
            f"at revision {approval.get('session_revision')}, {approval.get('created_at')}"
        )
        if approval.get("rationale"):
            lines.append(f"  - {approval['rationale']}")
        lines.append(f"  - bound to `{approval.get('target_digest')}`")
    lines.append("")
    return "\n".join(lines) + "\n"
