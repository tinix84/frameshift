"""Run the case through real commands; never prepare, answer, or bypass a gate.

Proposals are authored in Codex and imported, not independent model samples.
The proposal-only coordinator uses an unvalidated runtime profile, never a
manual-GUI attestation. Only a person launching bootstrap gui attests that mode.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from frameshift.orchestration.api import CommandRefused, SessionCoordinator
from frameshift.persistence.events import JsonlEventLog
from frameshift.validation import session_violations

STORE = HERE / "runtime-store"
MAP = HERE / "runtime-map.json"
REQUEST = "Can we now run this conversation through the actual FrameShift runtime, with the human checkpoints, and compare the result with your simulation?"
INTAKE = [
    ("observation", "Source turn 1, paraphrase: vehicle profit margin is reported at about 5 to 6 percent.", "sourced"),
    ("observation", "Source turn 1, paraphrase: battery pack price is reported to oscillate about 20 percent; the time period and matched specification are unknown.", "sourced"),
    ("outcome", "Source turn 1, paraphrase: compensate battery cost oscillation while preserving powertrain performance.", "sourced"),
    ("proposal", "Source turns 1 and 2, paraphrase: consider front-end DC/DC, different or mixed chemistries, or an integrated buck-boost Y-inverter.", "sourced"),
    ("assumption", "The previous assistant used a 40 percent battery share of original vehicle cost as an illustrative assumption, not a measured OEM value.", "assumed"),
    ("question", "ti sei chiesto perché la batteria varia del 20%? È dovuto a single source o è dovuto a supply chain stress?", "sourced"),
    ("proposal", "reconfiguring the battery can we have multiple power train (mostly motor+inverter SW) to follow battery pack oscillation?", "sourced"),
    ("constraint", "Source turn 1: preserve performance; the exact torque-speed, range, SOC, temperature and lifetime envelope needs human clarification.", "inferred"),
    ("question", "Which observed quotation, cost breakdown, supplier and qualification records distinguish market volatility from OEM-specific exposure?", "inferred"),
    ("assumption", "The battery decision is this session's concern. The source's later discussion of building and naming FrameShift is context, not a new objective for this session.", "assumed"),
]


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")


def coordinator():
    # Explicitly incapable of issuing trusted human approvals.
    profile = {"id":"profile_battery_codex_proposals", "validated":False}
    return SessionCoordinator(
        JsonlEventLog(STORE), approval_profile=profile,
        attestation={"operator":{"id":"runtime_codex_case_author", "kind":"runtime", "role":"reasoner"}},
        clock=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        new_suffix=lambda: secrets.token_hex(10),
    )


def add_once(co, mapping, key, collection, fields, add):
    state = co.state(mapping["session_id"])
    if key in mapping["ids"]:
        return
    used = set(mapping["ids"].values())
    # Recover a committed item if interrupted before saving the ID mapping.
    for item in collection(state):
        if item["id"] not in used and all(item.get(k)==v for k,v in fields.items()):
            mapping["ids"][key]=item["id"]
            write(MAP,mapping)
            return
    before = {item["id"] for item in collection(state)}
    add(state)
    (new,) = [x["id"] for x in collection(co.state(mapping["session_id"])) if x["id"] not in before]
    mapping["ids"][key]=new
    write(MAP,mapping)


def intake(co):
    if MAP.exists():
        mapping=read(MAP.name)
    else:
        sessions=co.sessions()
        if sessions:
            if len(sessions)!=1:
                raise SystemExit("Ambiguous store; inspect existing sessions before proceeding.")
            sid=sessions[0]["id"]
        else:
            sid=co.open_session(title="Battery architecture — source conversation runtime trial",request=REQUEST)["state"]["id"]
        mapping={"session_id":sid,"ids":{}}
        write(MAP,mapping)
    sid=mapping["session_id"]
    if co.state(sid)["phase"]!="intake":
        return mapping
    for i,(role,text,kind) in enumerate(INTAKE,1):
        provenance={"kind":kind,"source_ids":["art_shared_conversation"],"note":"Imported by Codex; sourced wording does not establish the underlying OEM facts."}
        fields={"text":text,"primary_role":role,"provenance":provenance}
        add_once(co,mapping,f"intake_item_{i:02}",lambda s:s["statements"],fields,
                 lambda s:co.add_statement(sid,expected_revision=s["revision"],**fields))
    state=co.state(sid)
    if "primary_role" not in state["statements"][0]:
        result={
            "schema_version":"1.0.0","execution_id":"exec_codex_battery_intake", "engine":"problem_framing",
            "input_revision":state["revision"],"status":"partial",
            "proposals":[{"id":"prop_classify_runtime_request","kind":"statement_classification","operation":"add",
                "value":{"statement_id":state["statements"][0]["id"],"primary_role":"need","secondary_roles":[]},
                "provenance":{"kind":"inferred","source_ids":[state["statements"][0]["id"]],"note":"Codex classifies the current human request to run the trial."}}],
            "rationale_summaries":["Keep the current runtime-test request distinct from imported battery claims. Imported observations remain sourced; no causal explanation or technology is approved."],
            "uncertainties":[],"conflicts":[],"missing_information":[{"id":"missing_oem_evidence","summary":"OEM quotations, cost basis, performance envelope and accountable owners remain unknown."}],
            "requested_capabilities":[],"required_checkpoints":["intake_correction"],
        }
        write(HERE / "runtime-intake.engine-result.json",result)
        admitted=co.admit_result(sid,result)
        assert admitted["outcome"]=="admitted",admitted
    return mapping


def framing(co,mapping,case):
    sid=mapping["session_id"]
    for i,f in enumerate(case["candidate_frames"],1):
        fields={
            "question":f["outcome"],"outcome":f["outcome"],
            "abstraction_level":f["abstraction_level"],"system_boundary":f["system_boundary"],
            "included":[f["outcome"]],"excluded":[f["exclusions"]],
            "success_measures":["Human to specify margin, switching cost/time and performance acceptance thresholds."],
            "constraints":["Preserve the agreed performance envelope; no automatic relaxation for derating."],
            "assumptions":["Reported margin and price movement require confirmation."],
            "open_questions":[f["owner"],f["lost_detail"]],
        }
        add_once(co,mapping,f["id"],lambda s:s["frames"],fields,
                 lambda s:co.propose_frame(sid,frame=fields,expected_revision=s["revision"]))
    levels=[("component","component","Adapt the electrical operating point","Converter cost and losses"),
            ("system","subsystem","Maintain traction performance across the battery operating envelope","Torque-speed-range map"),
            ("product","product","Enable qualified battery alternatives","Switching euros and weeks"),
            ("business","supply_chain","Protect vehicle margin and supply continuity","Agreed margin under matched scenarios")]
    for level,boundary,outcome,measure in levels:
        fields={"abstraction_level":level,"system_boundary":boundary,"outcome":outcome,
                "scope":outcome,"success_measures":[measure],"assumptions":["Ownership and target need human confirmation."],
                "loss":"Narrower framing omits commercial alternatives; wider framing loses detailed electrical constraints.",
                "provenance":{"kind":"inferred","source_ids":["art_shared_conversation"]}}
        add_once(co,mapping,"rung_"+level,lambda s:s.get("ladder",[]),fields,
                 lambda s:co.record_rung(sid,rung=fields,expected_revision=s["revision"]))
    # Human chooses and activates a candidate in the GUI; no default is imposed.


def causal(co,mapping,graph):
    sid=mapping["session_id"]
    for n in graph["nodes"]:
        fields={k:copy.deepcopy(v) for k,v in n.items() if k!="id"}
        add_once(co,mapping,n["id"],lambda s:s["graph"]["nodes"],fields,
                 lambda s:co.add_node(sid,node=fields,expected_revision=s["revision"]))
    for e in graph["edges"]:
        fields={k:copy.deepcopy(v) for k,v in e.items() if k!="id"}
        for key in ("source","target"):
            fields[key]=mapping["ids"][fields[key]]
        fields["provenance"]["source_ids"]=[mapping["ids"].get(x,x) for x in fields["provenance"]["source_ids"]]
        add_once(co,mapping,e["id"],lambda s:s["graph"]["edges"],fields,
                 lambda s:co.add_edge(sid,edge=fields,expected_revision=s["revision"]))


def compare(co,mapping,graph):
    sid=mapping["session_id"]
    state=co.state(sid)
    violations=session_violations(state)
    assert not violations,violations
    held={x["id"]:x for x in state["graph"]["nodes"]+state["graph"]["edges"]}
    reverse={v:k for k,v in mapping["ids"].items()}
    rows=[]
    for item in graph["nodes"]+graph["edges"]:
        actual=copy.deepcopy(held.get(mapping["ids"].get(item["id"])))
        if actual is None:
            differences=["not admitted: awaiting earlier human gate"]
        else:
            actual["id"]=reverse[actual["id"]]
            for key in ("source","target"):
                if key in actual:actual[key]=reverse.get(actual[key],actual[key])
            actual["provenance"]["source_ids"]=[reverse.get(x,x) for x in actual["provenance"]["source_ids"]]
            differences=[k for k in set(item)|set(actual) if item.get(k)!=actual.get(k)]
        rows.append({"reference_id":item["id"],"differences":differences})
    phase=state["phase"]
    frames_by_id={f["id"]:f for f in state["frames"]}
    frame_rows=[]
    for candidate in read("walkthrough.json")["candidate_frames"]:
        actual=frames_by_id.get(mapping["ids"].get(candidate["id"]))
        fields=("outcome","abstraction_level","system_boundary","status")
        frame_rows.append({"reference_id":candidate["id"],"runtime_id":actual["id"] if actual else None,
                           "differences":{k:{"simulation":candidate[k],"runtime":actual.get(k)} for k in fields if actual and candidate[k]!=actual.get(k)},
                           "admission":"admitted" if actual else "awaiting intake checkpoint"})
    report={"session_id":sid,"phase":phase,"revision":state["revision"],"events":len(co.history(sid)),
        "session_valid":True,"approval_count":len(state["approvals"]),
        "counts":{"statements":len(state["statements"]),"frames":len(state["frames"]),"rungs":len(state.get("ladder",[])),
                  "nodes":len(state["graph"]["nodes"]),"edges":len(state["graph"]["edges"])},
        "comparison":rows,"frame_comparison":frame_rows,"active_frame_id":state.get("active_frame_id"),
        "exact_graph_items":sum(not r["differences"] for r in rows),
        "next_step":{"intake":"Review classifications, then seal intake_correction on stmt_001 in the manual GUI.",
                     "framing":"Choose and activate one candidate, then seal frame_selection in the manual GUI.",
                     "causal":"Inspect graph and evidence gaps. Do not approve evidence_sufficiency without adequate evidence."}.get(phase,"No automated downstream stage is implemented for this case."),
        "limits":["Real coordinator admission and event replay; Codex-authored input, not an independent model reasoning-quality test.",
                  "Comparison normalizes generated IDs only. All semantic field differences are reported.",
                  "The proposed graph includes historical/meta nodes for comparison. They remain context, not a replacement battery objective.",
                  "Options, criteria and signed decision lack command/event coverage in this manual runtime (ADR-0022)."],
    }
    for name,data in [("runtime-state.json",state),("runtime-comparison.json",report),("runtime-events.json",co.history(sid))]:write(HERE/name,data)
    print(json.dumps({k:v for k,v in report.items() if k not in {"comparison","limits"}},ensure_ascii=True,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["advance","compare"],default="advance",nargs="?")
    args=parser.parse_args()
    graph=read("argument-graph.json");case=read("walkthrough.json");co=coordinator()
    mapping=read(MAP.name) if MAP.exists() else None
    if args.stage=="advance":
        mapping=intake(co)
        phase=co.state(mapping["session_id"])["phase"]
        if phase=="framing":framing(co,mapping,case)
        elif phase=="causal":causal(co,mapping,graph)
    if mapping is None:raise SystemExit("Run advance first.")
    compare(co,mapping,graph)


if __name__=="__main__":
    main()
