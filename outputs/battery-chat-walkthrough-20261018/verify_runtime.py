"""Non-destructive checks of this trial's real first checkpoint and browser export."""
from html.parser import HTMLParser
import json
import re
import subprocess

import runtime_driver as run


co=run.coordinator()
mapping=run.read(run.MAP.name)
sid=mapping["session_id"]
before=co.history(sid)
state=co.state(sid)
assert state["phase"]=="intake", "This first-checkpoint check is only for the initial intake."
assert not state["approvals"]
refusals=[]
for command in [
    lambda: co.propose_frame(sid,frame={"question":"Premature frame"},expected_revision=state["revision"]),
    lambda: co.add_node(sid,node={"type":"hypothesis","label":"Premature graph"},expected_revision=state["revision"]),
]:
    try:
        command()
    except run.CommandRefused as exc:
        assert exc.code=="invariant_violation",exc
        refusals.append({"code":exc.code,"detail":exc.detail})
    else:
        raise AssertionError("Runtime crossed a phase boundary without a human checkpoint")
assert co.history(sid)==before
run.intake(co)
assert co.history(sid)==before, "Rerunning intake added duplicate history"
assert not run.session_violations(co.state(sid))


class Export(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inner=None

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="iframe" and "data-srcdoc" in attrs:self.inner=attrs["data-srcdoc"]


export=run.HERE/"battery-chat-flow.html"
parser=Export()
parser.feed(export.read_text(encoding="utf-8"))
assert parser.inner and "__CASE_DATA__" not in parser.inner
payload=re.search(r'<script type="application/json" data-payload>(.*?)</script>',parser.inner,re.S)
assert payload
data=json.loads(payload.group(1))
assert len(data["case"]["stages"])==12
scripts=re.findall(r'<script>(.*?)</script>',parser.inner,re.S)
for script in scripts:
    check=subprocess.run(["node","--check","-"],input=script,text=True,encoding="utf-8",capture_output=True)
    assert check.returncode==0,check.stderr
report={"session_valid":True,"event_count":len(before),"phase":state["phase"],"approval_count":0,
        "phase_guard_refusals":refusals,"refusal_appended_nothing":True,"intake_rerun_idempotent":True,
        "standalone_has_populated_data":True,"javascript_syntax_valid":True,
        "browser_rendering":"Not inspected: browser tool disallows file URLs."}
run.write(run.HERE/"runtime-verification.json",report)
print(json.dumps(report,indent=2))
