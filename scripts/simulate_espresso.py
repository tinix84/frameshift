#!/usr/bin/env python3
"""Drive the espresso corpus case through the real application, one stage at a time.

`corpus/espresso-taste-complaint` is a hand-written reference session. This
script plays the reasoner's part in manual mode: it feeds the reference's
statements, ladder, frames and graph to the ordinary `SessionCoordinator`
commands, which validate them and write a real event log. It never approves a
gate. Between stages a person seals the gate in the manual GUI on the same
store, so every approval in the log is theirs (ADR-0002, ADR-0022).

    python scripts/simulate_espresso.py intake  --store .frameshift/espresso
    python -m frameshift.bootstrap gui --store .frameshift/espresso   # seal intake (same --store:
                                                                      # the GUI's default store differs)
    python scripts/simulate_espresso.py framing --store .frameshift/espresso
    python -m frameshift.bootstrap gui --store .frameshift/espresso   # seal frame selection
    python scripts/simulate_espresso.py causal  --store .frameshift/espresso
    python scripts/simulate_espresso.py compare --store .frameshift/espresso

`compare` can run after any stage. It reports, item by item, what the
application reproduced, what it could not represent, and anything it holds
that the reference does not; the gaps are the application's, not the case's
(epic #253). A stage runs once per store: the id map is saved after every item,
so an interrupted stage is refused rather than repeated.

The script speaks only as the reasoner. It never prepares or answers a gate,
and it offers every node and edge as `draft` or `proposed`: a status that
records a decision (rejected, superseded, approved) is the person's to make,
so the reference's decided statuses show up as differences (#254).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import manual_coordinator  # noqa: E402
from frameshift.orchestration.api import CommandRefused  # noqa: E402

CASE = ROOT / "corpus" / "espresso-taste-complaint"
REFERENCE = CASE / "espresso-taste-complaint.session.json"
TITLE = "Espresso taste complaint (simulation of the corpus case)"
MAP_FILE = "espresso-simulation.json"


def reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ id mapping


class Simulation:
    """The session id and the reference-to-application id map, kept beside the store."""

    def __init__(self, store: Path) -> None:
        self.path = store / MAP_FILE
        saved = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.session_id: str | None = saved.get("session_id")
        self.ids: dict[str, str] = saved.get("ids", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"session_id": self.session_id, "ids": self.ids}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def mapped(self, reference_ids: list[str]) -> list[str]:
        """Reference ids the application knows, translated; citations to outside artifacts kept."""
        return [self.ids.get(item, item) for item in reference_ids]


def _revision(co, sid: str) -> int:
    return co.state(sid)["revision"]


# A reasoner offers; only a person decides (AGENTS.md, #254).
REASONER_STATUSES = ("draft", "proposed")


def _offered(status: str) -> str:
    return status if status in REASONER_STATUSES else "proposed"


def _once(sim: Simulation, stage: str, reference_ids: list[str]) -> None:
    """Refuse a stage that already ran, wholly or in part, on this store."""
    done = [item for item in reference_ids if item in sim.ids]
    if done:
        raise SystemExit(
            f"the {stage} stage already ran on this store ({len(done)} of {len(reference_ids)} items added); "
            "start again from a fresh --store"
        )


def _new_ids(before: list[dict], after: list[dict]) -> list[str]:
    known = {item["id"] for item in before}
    return [item["id"] for item in after if item["id"] not in known]


# ---------------------------------------------------------------------- stages


def stage_intake(co, sim: Simulation, ref: dict) -> list[str]:
    if sim.session_id is not None:
        raise SystemExit(f"intake already ran: session {sim.session_id}")
    statements = ref["statements"]
    first = statements[0]
    sid = co.open_session(title=TITLE, request=first["text"])["state"]["id"]
    sim.session_id = sid
    sim.ids[first["id"]] = co.state(sid)["statements"][0]["id"]
    sim.save()
    # The request arrives unclassified; classifying it is a manual engine result.
    result = co.manual_framing_result(
        sid, [{"statement_id": sim.ids[first["id"]], "primary_role": first["primary_role"], "secondary_roles": []}]
    )
    co.admit_result(sid, result)
    for statement in statements[1:]:
        before = co.state(sid)["statements"]
        co.add_statement(
            sid, text=statement["text"], primary_role=statement["primary_role"], expected_revision=_revision(co, sid)
        )
        (new,) = _new_ids(before, co.state(sid)["statements"])
        sim.ids[statement["id"]] = new
        sim.save()
    sim.save()
    return [
        f"Session {sid} holds {len(statements)} statements and is in intake.",
        f"Seal intake in the GUI: gate intake_correction on {sim.ids[first['id']]}.",
    ]


def stage_framing(co, sim: Simulation, ref: dict) -> list[str]:
    sid = _require(co, sim, "framing")
    _once(sim, "framing", [rung["id"] for rung in ref["ladder"]] + [frame["id"] for frame in ref["frames"]])
    for rung in ref["ladder"]:
        before = co.state(sid).get("ladder", [])
        fields = {key: value for key, value in rung.items() if key != "id"}
        fields["provenance"] = dict(rung["provenance"], source_ids=sim.mapped(rung["provenance"]["source_ids"]))
        co.record_rung(sid, rung=fields, expected_revision=_revision(co, sid))
        (new,) = _new_ids(before, co.state(sid)["ladder"])
        sim.ids[rung["id"]] = new
        sim.save()
    working = None
    for frame in ref["frames"]:
        before = co.state(sid)["frames"]
        fields = {key: value for key, value in frame.items() if key not in {"id", "status", "digest"}}
        co.propose_frame(sid, frame=fields, expected_revision=_revision(co, sid))
        (new,) = _new_ids(before, co.state(sid)["frames"])
        sim.ids[frame["id"]] = new
        sim.save()
        if frame["status"] == "working":
            working = new
    co.activate_frame(sid, frame_id=working, expected_revision=_revision(co, sid))
    sim.save()
    return [
        f"Recorded {len(ref['ladder'])} rungs and proposed {len(ref['frames'])} frames; {working} is the working frame.",
        f"Seal framing in the GUI: gate frame_selection on {working}.",
    ]


def stage_causal(co, sim: Simulation, ref: dict) -> list[str]:
    sid = _require(co, sim, "causal")
    _once(sim, "causal", [node["id"] for node in ref["graph"]["nodes"]] + [edge["id"] for edge in ref["graph"]["edges"]])
    refused: list[str] = []
    graph = ref["graph"]
    for node in graph["nodes"]:
        before = co.state(sid)["graph"]["nodes"]
        fields = {
            "type": node["type"],
            "label": node["label"],
            "status": _offered(node["status"]),
            "confidence": node["confidence"],
            "source_ids": sim.mapped(node["provenance"]["source_ids"]),
        }
        for optional in ("description", "extensions"):
            if optional in node:
                fields[optional] = node[optional]
        try:
            co.add_node(sid, node=fields, expected_revision=_revision(co, sid))
        except CommandRefused as refusal:
            refused.append(f"node {node['id']}: {refusal}")
            continue
        (new,) = _new_ids(before, co.state(sid)["graph"]["nodes"])
        sim.ids[node["id"]] = new
        sim.save()
    for edge in graph["edges"]:
        if edge["source"] not in sim.ids or edge["target"] not in sim.ids:
            refused.append(f"edge {edge['id']}: an end was not added")
            continue
        before = co.state(sid)["graph"]["edges"]
        fields = {
            "source": sim.ids[edge["source"]],
            "target": sim.ids[edge["target"]],
            "type": edge["type"],
            "confidence": edge["confidence"],
        }
        try:
            co.add_edge(sid, edge=fields, expected_revision=_revision(co, sid))
        except CommandRefused as refusal:
            refused.append(f"edge {edge['id']}: {refusal}")
            continue
        (new,) = _new_ids(before, co.state(sid)["graph"]["edges"])
        sim.ids[edge["id"]] = new
        sim.save()
    sim.save()
    added = co.state(sid)["graph"]
    lines = [f"Added {len(added['nodes'])} nodes and {len(added['edges'])} edges."]
    lines += [f"Refused: {item}" for item in refused]
    return lines


def _require(co, sim: Simulation, phase: str) -> str:
    if sim.session_id is None:
        raise SystemExit("run the intake stage first")
    state = co.state(sim.session_id)
    if state["phase"] != phase:
        raise SystemExit(
            f"session {sim.session_id} is in {state['phase']!r}, not {phase!r}: "
            "seal the previous gate in the manual GUI first"
        )
    return sim.session_id


# --------------------------------------------------------------------- compare


def compare(state: dict, ref: dict, sim: Simulation) -> dict:
    """Item by item: what the application holds, against the reference."""
    back = {new: old for old, new in sim.ids.items()}

    def same(ref_item: dict, sim_item: dict | None, fields: list[str]) -> list[str]:
        if sim_item is None:
            return ["missing"]
        differences = []
        for field in fields:
            want, have = ref_item.get(field), sim_item.get(field)
            if field == "provenance" and isinstance(want, dict) and isinstance(have, dict):
                have = dict(have, source_ids=[back.get(item, item) for item in have.get("source_ids", [])])
            if want != have:
                differences.append(f"{field}: reference {_short(want)}, application {_short(have)}")
        return differences

    by_id = {}
    for section in ("statements", "frames", "ladder"):
        by_id.update({item["id"]: item for item in state.get(section, [])})
    by_id.update({item["id"]: item for item in state["graph"]["nodes"]})
    by_id.update({item["id"]: item for item in state["graph"]["edges"]})

    sections = {
        "statements": (ref["statements"], ["text", "primary_role", "status", "provenance"]),
        "ladder": (ref["ladder"], ["abstraction_level", "outcome", "scope", "system_boundary", "success_measures",
                                   "assumptions", "loss", "provenance"]),
        "frames": (ref["frames"], ["question", "outcome", "abstraction_level", "system_boundary", "included",
                                   "excluded", "success_measures", "constraints", "assumptions", "open_questions",
                                   "status"]),
        "nodes": (ref["graph"]["nodes"], ["type", "label", "status", "confidence", "description", "extensions",
                                          "provenance"]),
        "edges": (ref["graph"]["edges"], ["type", "status", "confidence", "extensions", "provenance"]),
    }
    held = {
        "statements": state.get("statements", []),
        "ladder": state.get("ladder", []),
        "frames": state.get("frames", []),
        "nodes": state["graph"]["nodes"],
        "edges": state["graph"]["edges"],
    }
    report: dict = {"sections": {}, "extra": {}}
    for name, (items, fields) in sections.items():
        mapped = {sim.ids.get(item["id"]) for item in items}
        report["extra"][name] = [item["id"] for item in held[name] if item["id"] not in mapped]
        rows = []
        for item in items:
            mine = by_id.get(sim.ids.get(item["id"], ""))
            if name == "edges" and mine is not None:
                ends = (back.get(mine["source"]), back.get(mine["target"]))
                if ends != (item["source"], item["target"]):
                    mine = None
            rows.append({"id": item["id"], "differences": same(item, mine, fields)})
        report["sections"][name] = rows
    report["session"] = {
        "phase": {"reference": ref["phase"], "application": state["phase"]},
        "active_frame": {
            "reference": ref["active_frame_id"],
            "application": back.get(state.get("active_frame_id"), state.get("active_frame_id")),
        },
        "approvals": {
            "reference": [(a["target_id"], a["disposition"], a["actor"]["id"]) for a in ref["approvals"]],
            "application": [
                (back.get(a["target_id"], a["target_id"]), a["disposition"], a["actor"]["id"])
                for a in state.get("approvals", [])
            ],
        },
        "extensions": {"reference": sorted(ref.get("extensions", {})), "application": sorted(state.get("extensions", {}))},
    }
    return report


def _short(value) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return text if len(text) <= 70 else text[:67] + "..."


def render(report: dict) -> str:
    lines = ["# Espresso simulation against the reference", ""]
    lines += ["| Section | Reference | Identical | Differs | Missing | Extra |", "|---|---|---|---|---|---|"]
    for name, rows in report["sections"].items():
        identical = sum(1 for row in rows if not row["differences"])
        missing = sum(1 for row in rows if row["differences"] == ["missing"])
        extra = len(report["extra"][name])
        lines.append(f"| {name} | {len(rows)} | {identical} | {len(rows) - identical - missing} | {missing} | {extra} |")
    lines += ["", "## Differences by field", "", "| Section | Field | Items differing |", "|---|---|---|"]
    for name, rows in report["sections"].items():
        counts: dict[str, int] = {}
        for row in rows:
            for difference in row["differences"]:
                if difference != "missing":
                    field = difference.split(":", 1)[0]
                    counts[field] = counts.get(field, 0) + 1
        for field, count in sorted(counts.items()):
            lines.append(f"| {name} | {field} | {count} of {len(rows)} |")
    lines += ["", "## Session", ""]
    for key, pair in report["session"].items():
        lines.append(f"- **{key}**: reference `{pair['reference']}`, application `{pair['application']}`")
    for name, extra in report["extra"].items():
        if extra:
            lines.append(f"- **extra {name}** (in the application, not in the reference): " + ", ".join(f"`{i}`" for i in extra))
    lines += ["", "## Differences by item", ""]
    for name, rows in report["sections"].items():
        for row in rows:
            if row["differences"]:
                lines.append(f"- `{row['id']}` ({name}): " + "; ".join(row["differences"]))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("stage", choices=["intake", "framing", "causal", "compare"])
    parser.add_argument("--store", type=Path, default=Path(".frameshift") / "espresso")
    args = parser.parse_args(argv)

    # The stages record no actor (they approve nothing), but a coordinator needs one.
    co = manual_coordinator(args.store, {"id": "user_local", "kind": "human", "role": "decision_owner"})
    sim = Simulation(args.store)
    ref = reference()
    if args.stage == "compare":
        if sim.session_id is None:
            raise SystemExit("nothing to compare: run the intake stage first")
        text = render(compare(co.state(sim.session_id), ref, sim))
        (args.store / "espresso-comparison.md").write_text(text, encoding="utf-8")
        print(text)
        return 0
    stage = {"intake": stage_intake, "framing": stage_framing, "causal": stage_causal}[args.stage]
    try:
        for line in stage(co, sim, ref):
            print(line)
    except CommandRefused as refusal:
        sim.save()
        print(f"The application refused: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
