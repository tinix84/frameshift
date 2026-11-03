"""Read-only UI fixture using the trial snapshot; never opens the approval GUI.

No route can write a session. The gate response only exercises dialog rendering.
The causal example is the authored simulation and is explicitly marked as such.
"""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from frameshift.bootstrap import gui_vocabulary
from frameshift.orchestration.sessions import frame_set, gates_available, ladder_order

state=json.loads((HERE/"runtime-state.json").read_text(encoding="utf-8"))
fixture=copy.deepcopy(state)
fixture["id"]="sess_graph_preview"
fixture["title"]="Battery reasoning graph — simulation preview, not approved runtime state"
fixture["phase"]="causal"
fixture["graph"]=json.loads((HERE/"argument-graph.json").read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    def send(self,value,code=200,kind="application/json"):
        raw=(json.dumps(value) if kind=="application/json" else value).encode("utf-8")
        self.send_response(code);self.send_header("Content-Type",kind+"; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)

    def do_GET(self):
        path=urlparse(self.path).path
        graph="graph" in urlparse(self.path).query or "sess_graph_preview" in path
        current=fixture if graph else state
        if path in {"/","/graph"}:
            page=(ROOT/"frameshift/gui/index.html").read_text(encoding="utf-8")
            page=page.replace("Manual mode. You write every proposal yourself, and approving here attests that no agent or model runs under your account.","READ-ONLY UI PREVIEW. No approvals or session changes can be recorded here.")
            if path=="/graph":page=page.replace("await refreshSessions();", "await refreshSessions(); await load('sess_graph_preview');")
            self.send(page,kind="text/html")
        elif path=="/api/meta":self.send({"operator":{"id":"preview_only","kind":"human","role":"decision_owner"},"vocabulary":gui_vocabulary()})
        elif path=="/api/sessions":self.send({"sessions":[{"id":state["id"],"title":state["title"],"phase":state["phase"],"revision":state["revision"]}]})
        elif path.startswith("/api/sessions/"):
            self.send({"state":current,"history":[],"derived":{"abstraction_required":False,"unclassified":[],"gates":gates_available(current),"frame_set":frame_set(current),"ladder_order":ladder_order(current),"held":[]}})
        else:self.send({},404)

    def do_POST(self):
        path=urlparse(self.path).path
        if path.endswith("/gates"):
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
            target=state["statements"][0]
            self.send({"confirmation_request":{"id":"preview_only","gate":body["gate"],"target_id":target["id"],"proposal":json.dumps(target),"session_revision":state["revision"],"target_digest":"preview-only","request_digest":"preview-only","actor":{"id":"preview_only","role":"decision_owner"}}})
        else:self.send({"code":"preview_read_only","detail":"UI preview only; no state is changed."},403)

    def do_DELETE(self):self.send({"outcome":"cancelled_preview"})
    def log_message(self,*args):pass


print("Read-only UI fixture at http://127.0.0.1:8766",flush=True)
ThreadingHTTPServer(("127.0.0.1",8766),Handler).serve_forever()
