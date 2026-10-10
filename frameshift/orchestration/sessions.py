"""The session coordinator: revision-bound commands over an event log (#6, #172).

This is the coordinator ADR-0015 names: every change to a session passes
through here, is checked against the phase it is standing in and the revision
its caller saw, is validated as the state it would produce, and only then is
appended to the log as one commit. Reads fold the log; nothing is cached that
could drift from it (ADR-0013).

It is the provider-neutral surface both inbound boundaries can drive. The MCP
server will call it with results a model produced; the manual GUI calls it
with results a person typed. The commands cannot tell the difference and do not
need to: an engine result is a contract (ADR-0006), not a provenance claim
about who filled it in.

What is here, by issue:

- #226 open a session from one verbatim request;
- #227 admit statement classifications from a problem-framing result, holding
  every other proposal kind for #7;
- #228 correct a classification, and derive whether abstraction is required;
- #229 seal a phase through its existing gate, with the existing trusted
  confirmation, appending the gate's own events;
- #238 keep an engine result's held proposals, and draft their adoption (ADR-0024);
- #239 seal framing only over two to five distinct candidate frames (ADR-0024);
- #237 record a rung of the abstraction ladder, or re-record it (ADR-0024);
- the shallow framing and causal steps the walking skeleton (#89) needs that
  the current event vocabulary already expresses: propose and activate a frame,
  add a graph node or edge.

Options, criteria and the decision itself have no events yet. The reducer
refuses an event type it does not know, and growing that vocabulary is
ADR-0013's deliberate act, so those columns are absent here rather than faked.
"""

from __future__ import annotations

import copy
from typing import Callable

from frameshift.contracts import errors
from frameshift.validation import session_violations, validate_against

from . import phases, proposals, replay, transitions
from .ports import EventLog, EventLogRefused

INVARIANT_VIOLATION = errors.INVARIANT_VIOLATION
REVISION_CONFLICT = errors.REVISION_CONFLICT
SCHEMA_INVALID = errors.SCHEMA_INVALID

SESSION_SCHEMA_VERSION = "2.0.0"
EMPTY_GRAPH = {"schema_version": "1.0.0", "nodes": [], "edges": []}

# #227: the proposal kinds intake admits - one, today. Everything else in a
# framing result is readable and held, never committed and never discarded.
# A set rather than a bare string constant: this is a proposal kind, not an
# error code, and the no-bare-code guard rightly cannot tell the two apart.
ADMITTED_KINDS = frozenset({"statement_classification"})

# #254: what a reasoner may say about its own node. Every other status records
# a decision (approved, rejected, superseded, archived), and a decision is a
# person's, reached through a gate, never a field a caller sets.
REASONER_NODE_STATUSES = ("draft", "proposed")

class CommandRefused(Exception):
    """A command that changed nothing, with a published code and the reason."""

    def __init__(self, code: str, detail: str, **extra) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.extra = extra

    def as_dict(self) -> dict:
        return {"outcome": "refused", "code": self.code, "detail": self.detail, **self.extra}


class SessionCoordinator:
    """Every read and write of a session, behind one revision check."""

    def __init__(
        self,
        log: EventLog,
        *,
        approval_profile: dict,
        attestation: dict,
        clock: Callable[[], str],
        new_suffix: Callable[[], str],
    ) -> None:
        self._log = log
        self._profile = copy.deepcopy(approval_profile)
        self._attestation = copy.deepcopy(attestation)
        self._clock = clock
        self._new_suffix = new_suffix
        # Pending confirmations live in memory only. A pending request is not
        # history: restarting the process forgets it, and the human asks again.
        self._pending: dict[str, tuple[str, object, dict]] = {}
        # ADR-0024 (#238): the last engine result's held proposals per session,
        # in memory on the same terms as pending confirmations. A restart
        # forgets them; a human re-runs the engine or re-reads.
        self._held: dict[str, dict] = {}

    # ----------------------------------------------------------------- reads

    @property
    def operator(self) -> dict:
        return copy.deepcopy(self._attestation["operator"])

    def sessions(self) -> list[dict]:
        listing = getattr(self._log, "session_ids", None)
        ids = listing() if callable(listing) else []
        found = []
        for session_id in ids:
            try:
                state = self.state(session_id)
            except CommandRefused:
                continue
            found.append(
                {
                    "id": state["id"],
                    "title": state["title"],
                    "phase": state["phase"],
                    "revision": state["revision"],
                }
            )
        return found

    def history(self, session_id: str) -> list[dict]:
        try:
            return self._log.read(session_id)
        except EventLogRefused as exc:
            raise CommandRefused(exc.code, exc.detail) from None

    def state(self, session_id: str) -> dict:
        history = self.history(session_id)
        if not history:
            raise CommandRefused(INVARIANT_VIOLATION, f"no session {session_id!r}")
        try:
            return replay.fold(history)
        except replay.ReplayRefused as exc:
            raise CommandRefused(exc.code, exc.detail) from None

    def view(self, session_id: str) -> dict:
        """State plus what is derived from it, never recorded (#228)."""
        state = self.state(session_id)
        return {
            "state": state,
            "derived": {
                "abstraction_required": abstraction_required(state),
                "unclassified": [s["id"] for s in state["statements"] if "primary_role" not in s],
                "gates": gates_available(state),
                "ladder_order": ladder_order(state),
                "frame_set": frame_set(state),
                "held": self._held_view(session_id, state),
                "pending_confirmations": [
                    request_id
                    for request_id, (owner, _, _) in self._pending.items()
                    if owner == session_id
                ],
            },
            "history": self.history(session_id),
        }

    # ------------------------------------------------------- intake (#226-#228)

    def open_session(self, *, title: str, request: str, workspace_id: str = "ws_local") -> dict:
        """#226: `session.created` then `statement.added`, the request byte for byte."""
        if not isinstance(request, str) or not request.strip():
            raise CommandRefused(SCHEMA_INVALID, "a session opens from a non-empty request")
        suffix = self._new_suffix()
        session_id = f"sess_{suffix}"
        created = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": session_id,
            "workspace_id": workspace_id,
            "title": title.strip() or request.strip()[:300],
            "status": "active",
            "phase": "intake",
            "revision": 0,
            "active_frame_id": None,
            "statements": [],
            "frames": [],
            "graph": copy.deepcopy(EMPTY_GRAPH),
            "options": [],
            "criteria": [],
            "approvals": [],
        }
        statement = {
            "id": "stmt_001",
            "text": request,
            "status": "draft",
            "provenance": {"kind": "observed", "source_ids": [f"intake_{suffix}"]},
        }
        bodies = [
            {"type": "session.created", "payload": created},
            {"type": "statement.added", "payload": statement},
        ]
        self._commit(session_id, [], bodies, revision=0)
        return self.view(session_id)

    def add_statement(
        self, session_id: str, *, text: str, primary_role: str, expected_revision: int
    ) -> dict:
        """A statement the reasoner adds during intake, already classified by them."""
        state = self._expect(session_id, expected_revision, phase="intake")
        statement = {
            "id": _next_id("stmt", state["statements"]),
            "text": text,
            "primary_role": primary_role,
            "secondary_roles": [],
            "status": "draft",
            "provenance": {
                "kind": "observed",
                "source_ids": [],
                "note": "Added by the reasoner during intake.",
            },
        }
        self._commit_next(state, [{"type": "statement.added", "payload": statement}])
        return self.view(session_id)

    def manual_framing_result(self, session_id: str, classifications: list[dict]) -> dict:
        """Build the problem-framing result a person authored in place of a model.

        The result is the same contract a model returns (ADR-0006) and is
        admitted by the same command. Building it is not committing it.
        """
        state = self.state(session_id)
        suffix = self._new_suffix()
        result = {
            "schema_version": "1.0.0",
            "execution_id": f"exec_manual_{suffix}",
            "engine": "problem_framing",
            "input_revision": state["revision"],
            "status": "complete",
            "proposals": [
                {
                    "id": f"prop_classify_{index:03d}",
                    "kind": "statement_classification",
                    "operation": "add",
                    "value": {
                        "statement_id": item.get("statement_id"),
                        "primary_role": item.get("primary_role"),
                        "secondary_roles": list(item.get("secondary_roles", [])),
                    },
                    "provenance": {
                        "kind": "inferred",
                        "source_ids": [item.get("statement_id")],
                        "note": "Entered manually by the operator; no model connected.",
                    },
                }
                for index, item in enumerate(classifications, start=1)
            ],
            "rationale_summaries": ["Classified manually by the operator."],
            "uncertainties": [],
            "conflicts": [],
            "missing_information": [],
            "requested_capabilities": [],
            "required_checkpoints": ["intake_correction"],
            "warnings": [],
        }
        violations = validate_against(result, "engine-result.schema.json")
        if violations:
            raise CommandRefused(SCHEMA_INVALID, "; ".join(violations))
        return result

    def admit_result(self, session_id: str, result: dict) -> dict:
        """#227: commit classifications; hold every other proposal; refuse a stale result."""
        violations = validate_against(result, "engine-result.schema.json")
        if violations:
            raise CommandRefused(SCHEMA_INVALID, "; ".join(violations))
        state = self.state(session_id)
        admission = proposals.admit(result, state)
        if admission["outcome"] != "admitted":
            code, _, detail = admission["refusals"][0].partition(": ")
            raise CommandRefused(code, detail, staleness=admission["staleness"])
        if state["phase"] != "intake":
            raise CommandRefused(
                INVARIANT_VIOLATION, f"classifications are admitted in intake, and the session is in {state['phase']!r}"
            )

        known = {statement["id"] for statement in state["statements"]}
        bodies, held = [], []
        for proposal in result["proposals"]:
            if proposal["kind"] not in ADMITTED_KINDS:
                held.append(proposal["id"])
                continue
            value = proposal["value"]
            if value.get("statement_id") not in known:
                raise CommandRefused(
                    INVARIANT_VIOLATION,
                    f"proposal {proposal['id']} classifies {value.get('statement_id')!r}, "
                    "which this session does not contain",
                )
            bodies.append(_classified(value["statement_id"], value.get("primary_role"), value.get("secondary_roles", [])))
        if bodies:
            self._commit_next(state, bodies)
        # Held as of the state this admission leaves behind: its own commit is
        # not news to it, and any later commit makes it stale. A result that
        # holds nothing (a manual classification) leaves an earlier one held.
        if held:
            self._held[session_id] = {
                "execution_id": result["execution_id"],
                "input_revision": state["revision"] + (1 if bodies else 0),
                "proposals": [copy.deepcopy(p) for p in result["proposals"] if p["kind"] not in ADMITTED_KINDS],
            }
        return {
            "outcome": "admitted" if bodies else "held",
            "committed": len(bodies),
            "held_proposal_ids": held,
            "view": self.view(session_id),
        }

    def correct_classification(
        self,
        session_id: str,
        *,
        statement_id: str,
        primary_role: str,
        secondary_roles: list[str],
        expected_revision: int,
    ) -> dict:
        """#228: a correction is another classification; the text cannot change."""
        state = self._expect(session_id, expected_revision, phase="intake")
        if statement_id not in {statement["id"] for statement in state["statements"]}:
            raise CommandRefused(INVARIANT_VIOLATION, f"no statement {statement_id!r} to correct")
        self._commit_next(state, [_classified(statement_id, primary_role, secondary_roles)])
        return self.view(session_id)

    # --------------------------------------------------------- framing (#7)

    def _held_view(self, session_id: str, state: dict) -> dict:
        held = self._held.get(session_id)
        if held is None:
            return {
                "execution_id": None,
                "stale": False,
                "by_kind": {},
                "note": "nothing held in this process: held proposals live in memory, "
                "and a restart forgets them; re-run the engine or re-read",
            }
        by_kind: dict[str, list[dict]] = {}
        for proposal in held["proposals"]:
            by_kind.setdefault(proposal["kind"], []).append(copy.deepcopy(proposal))
        return {
            "execution_id": held["execution_id"],
            "stale": held["input_revision"] != state["revision"],
            "by_kind": by_kind,
            "note": "held proposals are never committed as they stand; adopt one by "
            "issuing the ordinary command with the draft, edited as you see fit",
        }

    def held_draft(self, session_id: str, *, proposal_id: str) -> dict:
        """#238: a pre-filled, uncommitted draft of the command that adopts a proposal.

        Nothing is written. The human edits the draft and issues the ordinary
        command (`propose_frame`, or `record_rung` once per rung, passing the
        rung's `rung_id` when the ladder already holds that level); that command
        is the adoption, authored by the human, and the staleness rule stands.
        """
        held = self._held.get(session_id)
        proposal = next((p for p in (held or {}).get("proposals", []) if p["id"] == proposal_id), None)
        if proposal is None:
            raise CommandRefused(INVARIANT_VIOLATION, f"no held proposal {proposal_id!r} for this session")
        value = proposal.get("value") if isinstance(proposal.get("value"), dict) else {}
        # The engine's value is free-form under the result schema: keep what
        # can stand as written, and carry the provenance kind it declared.
        provenance = proposal.get("provenance") if isinstance(proposal.get("provenance"), dict) else {}
        declared = provenance.get("kind")
        cited = {
            "kind": declared if declared in PROVENANCE_KINDS else "inferred",
            "source_ids": _strings(provenance.get("source_ids")),
            "note": f"Adopted from held proposal {proposal_id}.",
        }
        if proposal["kind"] == "problem_frame":
            return {
                "kind": "problem_frame",
                "command": "propose_frame",
                "frame": {field: copy.deepcopy(value.get(field, "" if field in _FRAME_TEXT else [])) for field in _FRAME_FIELDS},
            }
        if proposal["kind"] == "abstraction_ladder":
            proposed = value.get("levels") if isinstance(value.get("levels"), list) else []
            levels = {level for level in proposed if isinstance(level, str) and level in LADDER_RANK}
            top = max(levels, key=LADDER_RANK.__getitem__, default=None)
            top_outcome = value.get("top_outcome") if isinstance(value.get("top_outcome"), str) else ""
            # One rung per level: a level already on the ladder is drafted as a
            # re-recording of that rung, never as a second rung beside it, and
            # from that rung's content, since a re-recording replaces it whole.
            recorded = {rung.get("abstraction_level"): rung for rung in self.state(session_id).get("ladder", [])}
            rungs = []
            for level in sorted(levels, key=LADDER_RANK.__getitem__):
                outcome = top_outcome if level == top else ""
                existing = recorded.get(level)
                if existing is None:
                    rungs.append(
                        {
                            "rung_id": None,
                            "abstraction_level": level,
                            "outcome": outcome,
                            "scope": "",
                            "system_boundary": "",
                            "success_measures": [],
                            "assumptions": [],
                            "loss": "",
                            "provenance": copy.deepcopy(cited),
                        }
                    )
                    continue
                draft = {key: copy.deepcopy(item) for key, item in existing.items() if key != "id"}
                draft["rung_id"] = existing["id"]
                if outcome:
                    # The proposal contributes only the top outcome; the rung
                    # cites the proposal only when it takes that contribution.
                    draft["outcome"] = outcome
                    draft["provenance"] = copy.deepcopy(cited)
                rungs.append(draft)
            return {"kind": "abstraction_ladder", "command": "record_rung", "rungs": rungs}
        raise CommandRefused(INVARIANT_VIOLATION, f"held proposals of kind {proposal['kind']!r} have no adoption path yet")

    def propose_frame(self, session_id: str, *, frame: dict, expected_revision: int) -> dict:
        """Add a candidate frame, proposed, with its content digest recorded."""
        state = self._expect(session_id, expected_revision, phase="framing")
        candidate = {
            "id": _next_id("frame", state["frames"]),
            "question": frame.get("question", ""),
            "outcome": frame.get("outcome", ""),
            "abstraction_level": frame.get("abstraction_level", ""),
            "system_boundary": frame.get("system_boundary", ""),
            "included": _strings(frame.get("included")),
            "excluded": _strings(frame.get("excluded")),
            "success_measures": _strings(frame.get("success_measures")),
            "constraints": _strings(frame.get("constraints")),
            "assumptions": _strings(frame.get("assumptions")),
            "open_questions": _strings(frame.get("open_questions")),
            "status": "proposed",
        }
        candidate["digest"] = transitions.content_digest(candidate)
        self._commit_next(state, [{"type": "frame.added", "payload": candidate}])
        return self.view(session_id)

    def record_rung(
        self,
        session_id: str,
        *,
        rung: dict,
        expected_revision: int,
        rung_id: str | None = None,
    ) -> dict:
        """#237: record one rung of the ladder, or re-record it to correct it.

        ADR-0024: without `rung_id` this adds a rung under a fresh id; with one
        it replaces that rung, and the earlier recording stays in the history.
        One rung per level is the validators' invariant, enforced on commit.
        """
        state = self._expect(session_id, expected_revision, phase="framing")
        ladder = state.get("ladder", [])
        if rung_id is not None and rung_id not in {item["id"] for item in ladder}:
            raise CommandRefused(INVARIANT_VIOLATION, f"no rung {rung_id!r} to re-record")
        recorded = {
            "id": rung_id or _next_id("rung", ladder),
            "abstraction_level": rung.get("abstraction_level", ""),
            "outcome": rung.get("outcome", ""),
            "scope": rung.get("scope", ""),
            "system_boundary": rung.get("system_boundary", ""),
            "success_measures": _strings(rung.get("success_measures")),
            "assumptions": _strings(rung.get("assumptions")),
            "loss": rung.get("loss", ""),
            "provenance": copy.deepcopy(
                rung.get("provenance")
                or {"kind": "assumed", "source_ids": [], "note": "Recorded by the operator."}
            ),
        }
        self._commit_next(state, [{"type": "ladder.rung.recorded", "payload": recorded}])
        return self.view(session_id)

    def activate_frame(self, session_id: str, *, frame_id: str, expected_revision: int) -> dict:
        """Make one candidate the working frame, ready for `frame_selection`.

        Activation changes a status, so it changes a digest. Every frame whose
        status moves gets its digest re-recorded in the same commit, so the
        digest a confirmation binds is never a stale one.
        """
        state = self._expect(session_id, expected_revision, phase="framing")
        if frame_id not in {frame["id"] for frame in state["frames"]}:
            raise CommandRefused(INVARIANT_VIOLATION, f"no frame {frame_id!r} to activate")
        bodies = [{"type": "frame.activated", "payload": {"id": frame_id}}]
        for frame in state["frames"]:
            # The reducer's rule for `frame.activated`, applied to a copy: the
            # previous working frame returns to proposed, this one works.
            moved = copy.deepcopy(frame)
            if moved["id"] == frame_id:
                moved["status"] = "working"
            elif moved["status"] == "working":
                moved["status"] = "proposed"
            if moved["status"] != frame["status"]:
                frame = moved
                bodies.append(
                    {
                        "type": "frame.digest.recorded",
                        "payload": {"id": frame["id"], "digest": transitions.content_digest(frame)},
                    }
                )
        self._commit_next(state, bodies)
        return self.view(session_id)

    # ---------------------------------------------------------- causal (#89)

    def add_node(self, session_id: str, *, node: dict, expected_revision: int) -> dict:
        """A reasoner-supplied node. Proposed, never established, by construction."""
        state = self._expect(session_id, expected_revision, phase="causal")
        status = node.get("status", "proposed")
        if status not in REASONER_NODE_STATUSES:
            raise CommandRefused(
                INVARIANT_VIOLATION,
                f"a reasoner offers a node as {' or '.join(REASONER_NODE_STATUSES)}, not {status!r}: "
                "a decided status is a person's, reached through a gate",
            )
        payload = {
            "id": _next_id("node", state["graph"]["nodes"]),
            "type": node.get("type", ""),
            "label": node.get("label", ""),
            "status": status,
            "confidence": node.get("confidence", "unknown"),
            "provenance": {
                "kind": "assumed",
                "source_ids": _strings(node.get("source_ids")),
                "note": "Supplied by the reasoner; not established.",
            },
        }
        if node.get("description"):
            payload["description"] = node["description"]
        if node.get("extensions"):
            payload["extensions"] = dict(node["extensions"])
        self._commit_next(state, [{"type": "graph.node.added", "payload": payload}])
        return self.view(session_id)

    def add_edge(self, session_id: str, *, edge: dict, expected_revision: int) -> dict:
        state = self._expect(session_id, expected_revision, phase="causal")
        payload = {
            "id": _next_id("edge", state["graph"]["edges"]),
            "source": edge.get("source", ""),
            "target": edge.get("target", ""),
            "type": edge.get("type", ""),
            "status": "proposed",
            "confidence": edge.get("confidence", "unknown"),
            "provenance": {
                "kind": "assumed",
                "source_ids": [edge.get("source", ""), edge.get("target", "")],
            },
        }
        if payload["type"] == "causes":
            # ADR-0003: a causal claim has an owner. Here it is the operator.
            payload["owner"] = self.operator
        self._commit_next(state, [{"type": "graph.edge.added", "payload": payload}])
        return self.view(session_id)

    # ------------------------------------------------------ gates (#229, #205)

    def prepare_gate(self, session_id: str, *, gate: str, target_id: str) -> dict:
        """The exact confirmation request a human must answer for this gate."""
        state = self.state(session_id)
        gate_spec = phases.GATES.get(gate)
        if gate_spec is None:
            raise CommandRefused(INVARIANT_VIOLATION, f"unknown gate {gate!r}")
        transition = {"gate": gate, "target_id": target_id, "to_phase": gate_spec.to_phase}
        refusal = transitions.sequence_refusal(state, transition)
        if refusal is not None:
            raise CommandRefused(refusal.code, refusal.detail)
        if transitions.find_target(state, target_id) is None:
            raise CommandRefused(INVARIANT_VIOLATION, f"no such target {target_id}")
        _require_frame_set(state, gate)
        # Imported here because `api` re-exports this coordinator.
        from .api import ConfirmationWorkflow

        workflow = ConfirmationWorkflow(state, self._profile)
        request_id = f"confirm_{self._new_suffix()}"
        request = workflow.prepare(transition, self._attestation, request_id=request_id)
        self._pending[request_id] = (session_id, workflow, transition)
        return request

    def confirm(self, request_id: str, response: dict) -> dict:
        """Bind a response to its pending request, then attempt the gate.

        Two existing guards decide, and nothing new is added (#229): the
        confirmation broker binds the response to the displayed request, and
        `transitions.attempt` applies sequence then binding. Only an accepted
        transition reaches the log.
        """
        entry = self._pending.get(request_id)
        if entry is None:
            raise CommandRefused(errors.APPROVAL_STALE, "no such pending confirmation request")
        session_id, workflow, transition = entry
        state = self.state(session_id)
        _require_frame_set(state, transition["gate"])
        workflow.replace_session(state)
        bound = workflow.complete(
            request_id,
            response,
            self._attestation,
            self._profile,
            confirmed_at=self._clock(),
        )
        if bound["outcome"] != "confirmed":
            if bound["outcome"] != "pending" or bound.get("code") != errors.SCHEMA_INVALID:
                self._pending.pop(request_id, None)
            raise CommandRefused(bound.get("code") or errors.APPROVAL_REQUIRED, bound.get("detail", ""))
        self._pending.pop(request_id, None)
        trusted = workflow.confirmation(request_id)
        outcome = transitions.attempt(state, transition, trusted)
        if outcome["outcome"] != "accepted":
            raise CommandRefused(outcome["code"], outcome["detail"])
        self._commit_next(state, outcome["events"])
        return {"outcome": "accepted", "phase": outcome["phase"], "view": self.view(session_id)}

    def cancel(self, request_id: str) -> None:
        self._pending.pop(request_id, None)

    # ----------------------------------------------------------- the commit

    def _expect(self, session_id: str, expected_revision: int, *, phase: str) -> dict:
        state = self.state(session_id)
        if type(expected_revision) is not int or expected_revision != state["revision"]:
            raise CommandRefused(
                REVISION_CONFLICT,
                f"command was formed against revision {expected_revision!r} and the session is at "
                f"{state['revision']}; re-read before acting",
            )
        if state["phase"] != phase:
            raise CommandRefused(
                INVARIANT_VIOLATION,
                f"this command belongs to phase {phase!r}, and the session is in {state['phase']!r}",
            )
        return state

    def _commit_next(self, state: dict, bodies: list[dict]) -> None:
        history = self.history(state["id"])
        self._commit(state["id"], history, bodies, revision=state["revision"] + 1)

    def _commit(self, session_id: str, history: list[dict], bodies: list[dict], *, revision: int) -> None:
        """Validate the state this commit would produce, then append it whole."""
        prospective = _as_events(session_id, history, bodies, revision)
        try:
            after = replay.fold(history + prospective)
        except (replay.ReplayRefused, KeyError) as exc:
            code = getattr(exc, "code", INVARIANT_VIOLATION)
            raise CommandRefused(code, getattr(exc, "detail", str(exc))) from None
        violations = session_violations(after)
        if violations:
            raise CommandRefused(SCHEMA_INVALID, "; ".join(violations))
        try:
            self._log.append(session_id, bodies, revision=revision)
        except EventLogRefused as exc:
            raise CommandRefused(exc.code, exc.detail) from None


# ------------------------------------------------------------------ derived


def abstraction_required(state: dict) -> bool:
    """#228: a proposal with no outcome serving it is a solution in disguise.

    Derived from state and never recorded, so it cannot disagree with the
    classifications it is read from.
    """
    live = [s for s in state.get("statements", []) if s.get("status") not in {"rejected", "superseded", "archived"}]
    has_proposal = any(s.get("primary_role") == "proposal" for s in live)
    has_outcome = any(s.get("primary_role") == "outcome" for s in live)
    return has_proposal and not has_outcome


# #238: the fields a held `problem_frame` value pre-fills; id, status and
# digest are FrameShift's to assign.
_FRAME_TEXT = ("question", "outcome", "abstraction_level", "system_boundary")
_FRAME_FIELDS = _FRAME_TEXT + ("included", "excluded", "success_measures", "constraints", "assumptions", "open_questions")


# The schema's provenance kinds (`common.schema.json`).
PROVENANCE_KINDS = frozenset({"observed", "sourced", "inferred", "assumed", "unknown"})


# ADR-0024: the ladder reads bottom to top by level rank, never by the order
# rungs were recorded. The rank is the schema enum's own order.
LADDER_RANK = {level: rank for rank, level in enumerate(("component", "subsystem", "system", "product", "business"))}


def ladder_order(state: dict) -> list[str]:
    """Rung ids from mechanism (how) up to outcome (why)."""
    rungs = [rung for rung in state.get("ladder", []) if rung.get("abstraction_level") in LADDER_RANK]
    return [rung["id"] for rung in sorted(rungs, key=lambda rung: LADDER_RANK[rung["abstraction_level"]])]


# ADR-0024: frame selection compares two to five live candidates.
LIVE_FRAME_STATUSES = frozenset({"proposed", "working"})
FRAME_SET_BOUNDS = (2, 5)


def _frame_axes(frame: dict) -> tuple:
    outcome = frame.get("outcome")
    outcome = outcome.strip().casefold() if isinstance(outcome, str) else outcome
    return (outcome, frame.get("abstraction_level"), frame.get("system_boundary"))


def frame_set(state: dict) -> dict:
    """#239: the live candidates, and which pairs fail to differ on any axis.

    Derived, never recorded. Two frames are indistinct when they agree on
    outcome (trimmed, case-folded), abstraction level, and system boundary.
    """
    live = [frame for frame in state.get("frames", []) if frame.get("status") in LIVE_FRAME_STATUSES]
    pairs = [
        [first["id"], second["id"]]
        for index, first in enumerate(live)
        for second in live[index + 1 :]
        if _frame_axes(first) == _frame_axes(second)
    ]
    low, high = FRAME_SET_BOUNDS
    return {
        "live": [frame["id"] for frame in live],
        "indistinct_pairs": pairs,
        "selectable": low <= len(live) <= high and not pairs,
    }


def frame_set_refusal(state: dict) -> str | None:
    """Why `frame_selection` may not be sealed on this state, or None (ADR-0024).

    A precondition on the sealing command, not a replay invariant: a history
    that passed the gate before this rule still folds.
    """
    report = frame_set(state)
    count, (low, high) = len(report["live"]), FRAME_SET_BOUNDS
    if count < low or count > high:
        listed = ", ".join(report["live"]) or "none"
        return (
            f"frame selection compares {low} to {high} live candidate frames, "
            f"and the session holds {count} ({listed})"
        )
    if report["indistinct_pairs"]:
        named = "; ".join(f"{a} and {b}" for a, b in report["indistinct_pairs"])
        return (
            "candidate frames must differ in outcome, abstraction level, or system "
            f"boundary, and these agree on all three: {named}"
        )
    return None


def gates_available(state: dict) -> list[dict]:
    """The gates passable from the current phase, with the targets each could bind."""
    phase = state.get("phase")
    available = []
    for name in phases.gates_from(phase):
        gate = phases.GATES[name]
        if not gate.advances:
            continue
        available.append(
            {
                "gate": name,
                "to_phase": gate.to_phase,
                "authority": sorted(transitions.GATE_AUTHORITY[name]),
                "targets": _targets_for(state, name),
            }
        )
    return available


def _targets_for(state: dict, gate: str) -> list[str]:
    if gate == "intake_correction":
        return [s["id"] for s in state.get("statements", []) if "primary_role" in s]
    if gate == "frame_selection":
        return [f["id"] for f in state.get("frames", []) if f.get("status") == "working"]
    if gate == "evidence_sufficiency":
        return [n["id"] for n in state.get("graph", {}).get("nodes", []) if n.get("type") == "hypothesis"]
    if gate in {"option_set_acceptance", "criteria_confirmation"}:
        return [o["id"] for o in state.get("options", [])] + [c["id"] for c in state.get("criteria", [])]
    if gate == "decision_approval":
        return [o["id"] for o in state.get("options", []) if o.get("status") == "selected"]
    return []


# ------------------------------------------------------------------ helpers


def _classified(statement_id: str, primary_role, secondary_roles) -> dict:
    return {
        "type": "statement.classified",
        "payload": {
            "id": statement_id,
            "primary_role": primary_role,
            "secondary_roles": list(secondary_roles or []),
        },
    }


def _as_events(session_id: str, history: list[dict], bodies: list[dict], revision: int) -> list[dict]:
    """The events the log would write, for validation before anything is written.

    Mirrors the log's placement rule (ADR-0013 as implemented by the JSON-lines
    store): creation carries its revision on itself, a later commit on its last
    event. The log stays the authority; a disagreement surfaces as its refusal.
    """
    fresh = not history
    carrier = 0 if fresh and bodies and bodies[0]["type"] == "session.created" else len(bodies) - 1
    events = []
    for offset, body in enumerate(bodies):
        event = {
            "type": body["type"],
            "payload": copy.deepcopy(body["payload"]),
            "session_id": session_id,
            "sequence": len(history) + offset + 1,
        }
        if offset == carrier:
            event["revision"] = revision
        events.append(event)
    return events


def _require_frame_set(state: dict, gate: str) -> None:
    if gate != "frame_selection":
        return
    refusal = frame_set_refusal(state)
    if refusal is not None:
        raise CommandRefused(INVARIANT_VIOLATION, refusal)


def _next_id(prefix: str, items: list[dict]) -> str:
    taken = {item.get("id") for item in items}
    number = len(items) + 1
    while f"{prefix}_{number:03d}" in taken:
        number += 1
    return f"{prefix}_{number:03d}"


def _strings(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [str(item).strip() for item in value if str(item).strip()]
