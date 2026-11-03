"""Build a source-mapped, unapproved walkthrough; does not call the coordinator."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from frameshift.validation.schema import validate_against

HERE = Path(__file__).parent
SOURCE = "https://chatgpt.com/share/6ad4942b-57a4-83ed-a9a5-5b98591088f2"
NODES = []
EDGES = []


def node(key, kind, label, turns, detail, basis="inferred"):
    NODES.append({
        "id": "node_" + key, "type": kind, "label": label,
        "status": "proposed", "confidence": "unknown",
        "provenance": {"kind": basis, "source_ids": ["art_shared_conversation"],
                       "note": "Conversation attribution only; not independent verification of its claims."},
        "description": detail,
        "extensions": {"source_turns": turns, "confidence_owner": "walkthrough_author"},
    })


def edge(a, b, kind):
    EDGES.append({"id": f"edge_{len(EDGES)+1:03}", "source": "node_"+a,
                  "target": "node_"+b, "type": kind, "status": "proposed",
                  "confidence": "unknown", "provenance": {"kind": "inferred",
                  "source_ids": ["node_"+a, "node_"+b],
                  "note": "Author reconstruction of a visible argument; no causal validation or human approval."}})


node("margin", "outcome", "Protect vehicle margin", [1,9,12], "Human's stated business concern. Margin definition, accountable owner, target, price policy and planning horizon remain unspecified.", "sourced")
node("price", "observation", "Pack price varies about 20%", [1,6], "Human-reported premise. Period, baseline, matched pack specification and quotation records are missing. Not an observed runtime intake.", "sourced")
node("thin", "observation", "Vehicle margin about 5–6%", [1], "Human-reported premise, not verified accounts. Gross contribution, EBIT and markup must not be treated as interchangeable.", "sourced")
node("share", "assumption", "Battery cost share = 40%", [1,12], "Assistant's illustrative assumption; not an OEM measurement.", "assumed")
node("shock", "hypothesis", "Price shock can erase margin", [1,3,12], "Conditional calculation: battery share times price change gives 8% of original cost, not automatically 8 percentage points of revenue margin. Requires stable sale price and other costs.")
node("dcdc", "intervention", "Add front-end DC/DC", [1], "Human proposal to decouple battery voltage from traction. Converter cost, duty cycle, losses, cooling, faults and qualification need measurement.", "sourced")
node("perf", "constraint", "Preserve vehicle performance", [1,9,12], "Human asks to preserve powertrain performance. Define torque-speed envelope, range, low-SOC policy, temperature and lifetime before comparison.", "sourced")
node("y", "intervention", "Integrated buck-boost Y-inverter", [2,3,12], "Human introduces ETH paper. This walkthrough records the proposal and citation, but does not independently validate the paper or transfer its benchmark results to a scooter.", "sourced")
node("cells", "hypothesis", "Fewer series cells means cheaper pack", [2], "Historical claim retained for audit. Lower series count alone does not establish fewer total cells at unchanged usable energy or range. No human rejection status is invented.", "sourced")
node("energy", "constraint", "Fixed energy constrains total cells", [3], "Counterargument: E = Ns × Np × Ecell. With identical cells and fixed installed energy, lower Ns requires higher Np. Usable-energy differences must be measured separately.")
node("util", "hypothesis", "Recover inaccessible usable energy", [2,3], "Battery reduction might follow if voltage limits genuinely strand usable energy. Illustrative utilization percentages in the chat are not measured results.")
node("current", "constraint", "Low voltage raises current demand", [2,3,4], "For fixed input power, I = P/V. Electrical, BMS, conductor and thermal limits can restrict any advantage of boost. Illustrative currents are not system validation.")
node("substitute", "hypothesis", "Lower battery substitution cost", [3,4,5,6,12], "Stronger candidate mechanism: qualified alternatives create sourcing options. Benefit depends on independent supply, actual availability, interfaces and total switching cost.")
node("variants", "intervention", "Prequalified powertrain variants", [4,12], "Human proposes motor/inverter/software variants. Common mechanics plus winding, current-rating and calibration variants are an assistant elaboration. Not approved architecture.", "sourced")
node("qual", "constraint", "Qualification cost and lead time", [4,6], "Variants must be usable when a sourcing opportunity occurs; inventory, service, EMC, reliability and homologation work cannot be presumed negligible.")
node("timing", "assumption", "Sourcing changes over months", [4,9], "Assistant timescale premise. Factory variants may suit procurement changes; runtime conversion may address SOC and load variation. These are distinct needs.", "assumed")
node("lithium", "hypothesis", "Raw-material pass-through", [1,5,6], "Initial lithium explanation remains a hypothesis. A lithium price change is not the same quantity as a cell or pack quotation change.")
node("single", "hypothesis", "Single-source dependency", [6,7], "Human raises single source as an alternative explanation, not a fact about the OEM. Requires supplier list, qualification and contract evidence.")
node("capacity", "hypothesis", "Capacity / allocation stress", [6,7], "Human raises supply-chain stress. Requires lead times, allocations, shortages and matched quotations.")
node("landed", "hypothesis", "FX, freight and contract effects", [6,7], "Other candidate explanations; none verified. Separate landed cost, pack integration, specification drift and supplier pricing.")
node("lock", "hypothesis", "Technical and commercial lock-in", [5,6,7], "Potential contributors include voltage, BMS, mechanical interfaces, qualification, MOQ and exclusivity. No one branch is established as the root cause.")
node("power", "hypothesis", "Supplier pricing power", [6,7], "High switching cost may reduce bargaining options. The chat's proposed AND gate is not a validated necessary-and-sufficient causal law.")
node("quotes", "evidence", "Request comparable quotations", [6,12], "REQUEST ONLY: historical matched-spec quotes/invoices, volume, supplier, currency, delivery terms, indices and contract changes. No dataset was supplied.")
node("sweep", "evidence", "Request duty-cycle / voltage sweep", [2,3,12], "REQUEST ONLY: torque-speed-SOC-temperature maps, usable energy, cell/BMS current limits and duty-weighted losses. No experiment was run.")
node("dual", "intervention", "Standard interfaces + dual sourcing", [1,6,12], "Targets technical/commercial substitution barriers. Correlated upstream suppliers or capacity constraints may limit diversification value.")
node("corner", "intervention", "VSI + derating or corner boost", [3,12], "Alternative technical branch. Derating changes the performance envelope and requires an explicit human relaxation if it violates the original constraint.")
node("baseline", "intervention", "Keep current design / learn first", [1,3,12], "Explicit comparison baseline added by this translation. Learning has cost and delay; no architecture change is committed.")
node("commercial", "intervention", "Contracts / leasing / price policy", [1,6,9,12], "Alternative business and procurement interventions. Leasing reallocates exposure; it does not make risk disappear from the combined system.")
node("cost", "hypothesis", "Compare lifecycle scenario cost", [4,12], "Proposed method: battery + traction + NRE + validation + inventory/service + energy/lifetime effects, under matched performance and sourcing scenarios. No supported winner or weights yet.")
node("pending", "decision", "Decision pending human review", [12], "No approved frame, criteria, evidence-sufficiency finding or architecture decision exists in this reconstruction. Conversation preferences are retained as proposals.")
node("linear", "hypothesis", "Five Whys misses alternative branches", [5,6,7], "Human critiques shallow exploration after challenging the initial cause. More depth alone does not establish causal correctness.", "sourced")
node("breadth", "intervention", "Branch, test, attach evidence", [7], "Use multiple explanations, missing-condition questions and discriminating evidence. Literature mentions in the chat remain unverified source references.")
node("tool", "outcome", "Build an inspectable reasoning tool", [8,9,10,11], "A separate concern emerges: a model-agnostic tool for framing, causal analysis, options and human decisions. Link it to this case without replacing the battery objective.", "sourced")
node("graph", "intervention", "Typed JSON graph; Mermaid view", [8], "Current ADR-0003 matches the broad proposal. Historical example statuses, probability 0.65 and generic CAUSES are not copied into current canonical objects.")
node("reframe", "intervention", "Why/how ladder + boundary review", [9], "Human explicitly requests stepping back from component selection to the business outcome. Current contract separates abstraction from boundary; time is descriptive.", "sourced")
node("return", "outcome", "Return to battery strategy narrative", [12,13], "Prompt 12 asks for in-chat slides, prompt 13 for Typst/PDF. Those are historical requests in the source, not new execution instructions in this task.", "sourced")

for a,b,k in [
    ("thin","shock","supports"),("price","shock","supports"),("share","shock","supports"),("shock","margin","worsens"),
    ("dcdc","perf","enables"),("y","perf","enables"),("perf","y","constrains"),
    ("y","cells","supports"),("energy","cells","contradicts"),("current","y","constrains"),
    ("y","util","enables"),("sweep","util","tests"),("sweep","y","tests"),
    ("y","substitute","enables"),("variants","substitute","enables"),("qual","variants","constrains"),
    ("timing","variants","supports"),("substitute","margin","contributes_to"),
    ("lithium","price","contributes_to"),("capacity","price","contributes_to"),("landed","price","contributes_to"),
    ("lock","single","contributes_to"),("lock","power","contributes_to"),("single","power","contributes_to"),("power","price","contributes_to"),
    ("quotes","lithium","tests"),("quotes","power","tests"),("quotes","capacity","tests"),
    ("dual","lock","addresses"),("dual","single","addresses"),("variants","lock","addresses"),
    ("corner","perf","constrains"),("qual","cost","contributes_to"),("current","cost","contributes_to"),
    ("baseline","cost","derived_from"),("y","cost","requires"),("variants","cost","requires"),
    ("commercial","margin","addresses"),("cost","pending","supports"),
    ("linear","breadth","supports"),("breadth","tool","supports"),("graph","tool","enables"),
    ("reframe","tool","enables"),("reframe","margin","addresses"),("return","margin","derived_from"),
]:
    edge(a,b,k)


def stage(title, turns, focus, delta, gate, question):
    return {"title": title, "turns": turns, "focus": ["node_"+x for x in focus.split()],
            "rationale_summary": delta, "checkpoint": gate, "next_question": question}


STAGES = [
    stage("1 · Intake: outcome versus mechanism", [1], "margin thin price share shock dcdc perf", "Preserve the user's business concern and performance constraint; classify DC/DC and chemistry changes as proposals. The 40% share comes from the assistant.", "Intake correction pending", "Which margin measure, pack specification, period and performance envelope are intended?"),
    stage("2 · First technical branch", [2], "margin y perf cells util current", "The Y-inverter is introduced. The assistant initially strengthens the cheaper-pack argument, but examples do not prove vehicle-level economics.", "Frame selection pending", "Is the concern voltage-limited performance, inaccessible usable energy, or procurement substitution?"),
    stage("3 · Contradiction retained", [3], "y cells energy util sweep current", "Keep the earlier cell-saving claim and connect its counterargument. Separate series count, total energy, usable energy and current limits.", "Evidence sufficiency pending", "How much usable energy is actually inaccessible under the required duty cycle?"),
    stage("4 · Manufacturing alternative", [4], "variants substitute qual timing current margin", "Add a distinct intervention: prequalified powertrain families. The assistant preference changes; this is not a human selection.", "Option-set acceptance pending", "Do switching savings exceed NRE, qualification, inventory and service costs?"),
    stage("5 · Five Whys narrows too soon", [5], "margin price lithium lock single power", "The explanation gravitates to architectural lock-in. FrameShift should retain that as a hypothesis and seek competing causes before declaring a root cause.", "Evidence sufficiency pending", "What else could explain the same quotation movement?"),
    stage("6 · Human expands the causal model", [6], "lithium capacity landed quotes price lock single power dual", "The human challenges the assumed cause: single source or supply stress? Introduce alternatives and request evidence; do not record single source as a fact.", "Evidence sufficiency pending", "Do matched quotes support raw-material, supplier-power, capacity or landed-cost explanations?"),
    stage("7 · From a chain to a graph", [7], "linear breadth lock single power price lithium capacity quotes", "Add breadth and causal tests. Treat AND/OR examples and correlation numbers in the conversation as illustrations, not established gates or measured results.", "Causal claims remain proposals", "Which observation would distinguish the competing mechanisms?"),
    stage("8 · A linked product concern", [8], "linear breadth tool graph margin", "A second concern emerges: build an interactive reasoning system. Link the battery case as motivating evidence; keep its unresolved objective visible.", "New concern / frame review pending", "Are we designing the tool or solving the battery case in this session?"),
    stage("9 · Explicit reframing", [9], "dcdc perf substitute margin reframe tool dual commercial", "Separate the why/how ladder from cause/effect. Business framing opens procurement and commercial options; wider scope still needs an accountable owner.", "Working-frame approval pending", "Who can authorize the business boundary and own success measures?"),
    stage("10 · Naming and repository branch", [10,11], "tool graph reframe margin", "The source navigator records naming and a public-repository request. The detailed assistant turns 10–11 were not inspected; no repository execution is inferred from them.", "Historical branch only", "What was actually created and validated, versus merely proposed in the conversation?"),
    stage("11 · Return to the original outcome", [12,13], "return margin variants y dual commercial baseline cost pending", "The slide narrative returns to margin. It offers an architecture preference without OEM evidence, approved criteria or a signed decision. A document request is not validation.", "Decision approval pending", "What evidence and human-owned criteria would justify selecting an architecture?"),
    stage("12 · FrameShift handoff", [1,3,4,6,9,12], "quotes sweep baseline variants y dual cost pending", "Proposed next sequence: correct intake; approve one frame; gather evidence; accept an option set including baseline; confirm criteria; compare scenarios; ask for a decision.", "Stop before real gate transitions", "Which candidate frame should a human approve for a real runtime session?"),
]

CASE = {
    "artifact_type": "conversation_translation_walkthrough", "source_url": SOURCE,
    "source_title": "Battery Cost Architecture", "source_accessed": "2026-10-18",
    "source_coverage": {"inspected_turn_pairs": [1,2,3,4,5,6,7,8,9,12,13], "navigator_only_turns": [10,11]},
    "execution": "Offline authored reconstruction. No model engine, coordinator command, event log, approval or real session was executed.",
    "authority": "All graph objects proposed; all confidence bands unknown. Stage navigation is presentation only, not approval.",
    "artifacts": {"art_shared_conversation": {"url": SOURCE, "kind": "source_reference", "capture": "Visible conversation read in browser; summaries are paraphrases, not a verbatim transcript."}},
    "stages": STAGES,
    "candidate_frames": [
        {"id":"candidate_business", "abstraction_level":"business", "system_boundary":"supply_chain", "status":"proposed", "outcome":"Maintain agreed margin and supply continuity under battery price and availability scenarios.", "owner":"OEM business owner to confirm", "exclusions":"Converter choice is not fixed.", "lost_detail":"Electrical requirements need a linked technical frame."},
        {"id":"candidate_product", "abstraction_level":"product", "system_boundary":"product", "status":"proposed", "outcome":"Enable economically qualified battery alternatives while preserving agreed customer performance.", "owner":"Platform owner to confirm", "exclusions":"Customer pricing and leasing policy outside this candidate boundary.", "lost_detail":"Cannot alone remove correlated market exposure."},
        {"id":"candidate_traction", "abstraction_level":"system", "system_boundary":"subsystem", "status":"proposed", "outcome":"Meet agreed torque-speed-range envelope over specified battery and operating limits.", "owner":"Powertrain owner to confirm", "exclusions":"Supplier and commercial strategy outside this candidate boundary.", "lost_detail":"Cannot establish the full business case from electrical performance alone."},
    ],
    "evidence_requests": [
        {"id":"request_quotes", "targets":["node_lithium","node_capacity","node_power","node_landed"], "request":"Matched-spec pack/cell quote and invoice history; currency, volume, supplier, contracts, indices, freight and specification changes.", "discriminates":"Whether similar market moves produce different OEM price outcomes; correlation alone does not prove causation."},
        {"id":"request_switch", "targets":["node_lock","node_single","node_substitute"], "request":"Qualified supplier list; itemized € and weeks to change pack; shared upstream exposure; BMS/mechanical/electrical and validation barriers.", "discriminates":"Whether the principal substitution barrier is electrical, qualification, commercial or capacity."},
        {"id":"request_duty", "targets":["node_util","node_y","node_corner"], "request":"Measured battery/motor operating maps and representative duty cycles, temperature and aging conditions.", "discriminates":"Whether boost recovers useful energy or chiefly preserves peak performance in a limited operating region."},
        {"id":"request_cost", "targets":["node_cost","node_variants","node_pending"], "request":"Volume and lifetime assumptions; BOM/NRE/validation/inventory/service/loss/lifetime costs; named criteria owners and scenario set.", "discriminates":"Whether variants, universal conversion, sourcing changes or baseline perform best under the same constraints."},
    ],
    "numerical_audit": {
        "warning":"Illustrative premises only; no current price or investment recommendation.",
        "model":"Assume sale price P=100, original revenue-based margin m=0.06, cost C=94, battery share b=0.40 of C, pack price shock d=0.20; hold price and all other costs fixed.",
        "battery_cost":37.6, "cost_increase":7.52, "new_cost":101.52, "new_margin_fraction":-0.0152,
        "interpretation":"8% is the increase relative to original cost. It is 7.52 percentage points of revenue here; margin changes from 6% to -1.52%.",
        "smaller_pack_warning":"After a 10% reduction of the original battery cost, a subsequent 20% price shock gives C=97.008 and margin 2.992%, before added converter cost. The chat's shortcut omitted the upfront saving. This does not establish a viable hedge.",
        "cell_count_warning":"14s8p=112 cells; 12s10p=120 cells. This refutes an automatic cell-count saving at similar installed energy, not every possible usable-energy benefit.",
    },
    "test_findings": [
        "Preserve counterarguments instead of overwriting prior claims.",
        "Human suggestions of single source and capacity stress are not measured OEM facts.",
        "The assistant repeatedly changes its preferred topology; no approved decision follows.",
        "A broader frame is a candidate and needs an owner; it is not automatically superior.",
        "The historical JSON example mixes epistemic type and lifecycle status; use current schema types and ordinal confidence.",
        "Do not infer causal AND/OR gates or confidence probabilities from illustrative prose.",
        "Factory sourcing timescales and runtime SOC variation need separate requirements.",
        "The complete map is a typed directed graph, not a tree: evidence, contradictions and shared interventions create cross-links.",
    ],
}

if __name__ == "__main__":
    graph = {"schema_version":"1.0.0", "nodes":NODES, "edges":EDGES}
    errors = validate_against(graph, "graph.schema.json")
    ids = {n["id"] for n in NODES}
    assert len(ids) == len(NODES)
    assert all(e["source"] in ids and e["target"] in ids for e in EDGES)
    assert all(set(s["focus"]) <= ids for s in STAGES)
    assert not errors, errors
    for filename, data in [("argument-graph.json", graph), ("walkthrough.json", CASE)]:
        (HERE / filename).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    template = (HERE / "view.fragment.html").read_text(encoding="utf-8")
    payload = json.dumps({"graph":graph,"case":CASE}, ensure_ascii=False).replace("<", "\\u003c")
    dest = Path(r"C:\Users\tinix\.codex\visualizations\2026\10\18\01a14e63-505a-73c1-b3e8-811f8f51365f\battery-chat-flow.html")
    dest.write_text(template.replace("__CASE_DATA__", payload), encoding="utf-8")
    print(f"Validated {len(NODES)} proposed nodes, {len(EDGES)} proposed edges, {len(STAGES)} walkthrough stages.")
    print(dest)
