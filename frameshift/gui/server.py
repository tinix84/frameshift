"""The manual GUI's HTTP boundary (ADR-0022, proposed).

A peer of `frameshift.mcp`: it translates a protocol into application
operations and grants no authority by itself. It imports `contracts` and
`orchestration.api` and nothing else of the application, and only `bootstrap`
assembles it.

Standard library only, like the rest of the repository. The page and its
script are one static file; every route below is JSON in, JSON out.

The server is meant for one person. Locally, three things keep it that way, and
none of them is a substitute for ADR-0014's trust boundary:

- it binds to the loopback interface and refuses a `Host` header that does not
  name it, which closes DNS rebinding;
- every API call must carry the per-launch token embedded in the page, in a
  custom header, which a cross-origin page cannot send without a preflight this
  server never answers;
- no model is connected, so no tool call can reach a route.

Hosted (ADR-0022, hosted mode), it listens on all interfaces behind the
platform's TLS proxy, accepts only the configured public host name, and every
request - the page included - must also carry HTTP Basic credentials matching
the deployment password. The launch token stays: a browser resends Basic
credentials on a cross-site request by itself, but it cannot add the custom
token header without a preflight, so the token is what stops a hostile page
from driving the API with the operator's login.
"""

from __future__ import annotations

import base64
import hmac
import json
import re
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from frameshift.contracts import errors
from frameshift.orchestration.api import CommandRefused, SessionCoordinator

PAGE = Path(__file__).with_name("index.html")
TOKEN_HEADER = "X-FrameShift-Token"
MAX_BODY = 1_048_576

# Published codes map to HTTP statuses so a client can branch without parsing
# prose. Anything unmapped is a 422: the request was understood and refused.
STATUS_FOR_CODE = {
    errors.REVISION_CONFLICT: HTTPStatus.CONFLICT,
    errors.APPROVAL_STALE: HTTPStatus.CONFLICT,
    errors.APPROVAL_REQUIRED: HTTPStatus.FORBIDDEN,
    errors.UNSUPPORTED_CONFIGURATION: HTTPStatus.FORBIDDEN,
}

SESSION = r"(?P<sid>[A-Za-z0-9][A-Za-z0-9._-]{2,127})"
ROUTES = [
    ("GET", r"^/api/meta$", "meta"),
    ("GET", r"^/api/sessions$", "list_sessions"),
    ("POST", r"^/api/sessions$", "open_session"),
    ("GET", rf"^/api/sessions/{SESSION}$", "view"),
    ("GET", rf"^/api/sessions/{SESSION}/record$", "record"),
    ("POST", rf"^/api/sessions/{SESSION}/manual-result$", "manual_result"),
    ("POST", rf"^/api/sessions/{SESSION}/engine-result$", "admit_result"),
    ("POST", rf"^/api/sessions/{SESSION}/statements$", "add_statement"),
    ("POST", rf"^/api/sessions/{SESSION}/corrections$", "correct"),
    ("POST", rf"^/api/sessions/{SESSION}/frames$", "propose_frame"),
    ("POST", rf"^/api/sessions/{SESSION}/frames/(?P<fid>[A-Za-z0-9._:-]+)/activate$", "activate_frame"),
    ("POST", rf"^/api/sessions/{SESSION}/nodes$", "add_node"),
    ("POST", rf"^/api/sessions/{SESSION}/edges$", "add_edge"),
    ("POST", rf"^/api/sessions/{SESSION}/gates$", "prepare_gate"),
    ("POST", r"^/api/confirmations/(?P<rid>[A-Za-z0-9._:-]+)$", "confirm"),
    ("DELETE", r"^/api/confirmations/(?P<rid>[A-Za-z0-9._:-]+)$", "cancel"),
]


class ManualApp:
    """Route table to coordinator calls. No state of its own beyond the token."""

    def __init__(
        self,
        coordinator: SessionCoordinator,
        *,
        token: str,
        vocabulary: dict,
        record,
        password: str | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.token = token
        self.password = password
        self.vocabulary = vocabulary
        self._record = record
        # One command at a time: the log checks revisions, but two threads
        # reading the same revision would race to a refusal nobody caused.
        self.lock = threading.Lock()

    def meta(self, body, **_):
        return {
            "mode": "manual",
            "model_connected": False,
            "operator": self.coordinator.operator,
            "vocabulary": self.vocabulary,
        }

    def list_sessions(self, body, **_):
        return {"sessions": self.coordinator.sessions()}

    def open_session(self, body, **_):
        return self.coordinator.open_session(title=body.get("title", ""), request=body.get("request", ""))

    def view(self, body, sid):
        return self.coordinator.view(sid)

    def record(self, body, sid):
        return {"markdown": self._record(self.coordinator.state(sid))}

    def manual_result(self, body, sid):
        return {"result": self.coordinator.manual_framing_result(sid, body.get("classifications", []))}

    def admit_result(self, body, sid):
        return self.coordinator.admit_result(sid, body.get("result", {}))

    def add_statement(self, body, sid):
        return self.coordinator.add_statement(
            sid,
            text=body.get("text", ""),
            primary_role=body.get("primary_role", ""),
            expected_revision=body.get("expected_revision"),
        )

    def correct(self, body, sid):
        return self.coordinator.correct_classification(
            sid,
            statement_id=body.get("statement_id", ""),
            primary_role=body.get("primary_role", ""),
            secondary_roles=body.get("secondary_roles", []),
            expected_revision=body.get("expected_revision"),
        )

    def propose_frame(self, body, sid):
        return self.coordinator.propose_frame(
            sid, frame=body.get("frame", {}), expected_revision=body.get("expected_revision")
        )

    def activate_frame(self, body, sid, fid):
        return self.coordinator.activate_frame(sid, frame_id=fid, expected_revision=body.get("expected_revision"))

    def add_node(self, body, sid):
        return self.coordinator.add_node(sid, node=body.get("node", {}), expected_revision=body.get("expected_revision"))

    def add_edge(self, body, sid):
        return self.coordinator.add_edge(sid, edge=body.get("edge", {}), expected_revision=body.get("expected_revision"))

    def prepare_gate(self, body, sid):
        return {
            "confirmation_request": self.coordinator.prepare_gate(
                sid, gate=body.get("gate", ""), target_id=body.get("target_id", "")
            )
        }

    def confirm(self, body, rid):
        return self.coordinator.confirm(rid, body.get("response", {}))

    def cancel(self, body, rid):
        self.coordinator.cancel(rid)
        return {"outcome": "cancelled"}


def make_handler(app: ManualApp, allowed_hosts: frozenset[str]):
    compiled = [(method, re.compile(pattern), name) for method, pattern, name in ROUTES]

    class Handler(BaseHTTPRequestHandler):
        server_version = "FrameShiftManual/0.1"

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            return  # request lines are not session state; keep the terminal quiet

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method: str) -> None:
            host = self.headers.get("Host", "")
            if host not in allowed_hosts:
                print(f"refused Host header {host!r}; served: {sorted(allowed_hosts)}", file=sys.stderr)
                return self._json(HTTPStatus.MISDIRECTED_REQUEST, _refusal("host not served here"))
            if app.password is not None and not _basic_matches(self.headers.get("Authorization", ""), app.password):
                data = json.dumps(_refusal("login required")).encode("utf-8")
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="FrameShift", charset="UTF-8"')
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return None
            path = urlparse(self.path).path
            if method == "GET" and path in {"/", "/index.html"}:
                return self._page()
            if self.headers.get(TOKEN_HEADER) != app.token:
                return self._json(HTTPStatus.FORBIDDEN, _refusal("missing or wrong launch token"))
            for route_method, pattern, name in compiled:
                match = pattern.match(path)
                if match and route_method == method:
                    try:
                        body = self._body() if method == "POST" else {}
                        with app.lock:
                            result = getattr(app, name)(body, **match.groupdict())
                        return self._json(HTTPStatus.OK, result)
                    except CommandRefused as refused:
                        status = STATUS_FOR_CODE.get(refused.code, HTTPStatus.UNPROCESSABLE_ENTITY)
                        return self._json(status, refused.as_dict())
                    except ValueError as exc:
                        return self._json(HTTPStatus.BAD_REQUEST, _refusal(str(exc), errors.SCHEMA_INVALID))
            return self._json(HTTPStatus.NOT_FOUND, _refusal(f"no route {method} {path}"))

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("request body exceeds 1 MiB")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"request body is not JSON: {exc}") from None
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
            return body

        def _page(self) -> None:
            html = PAGE.read_text(encoding="utf-8").replace("__FRAMESHIFT_TOKEN__", app.token)
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'",
            )
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(
    app: ManualApp,
    *,
    port: int,
    host: str = "127.0.0.1",
    public_hosts: tuple[str, ...] = (),
) -> ThreadingHTTPServer:
    """Bind and return the server; the caller runs it.

    Loopback by default. Any other bind requires a password on the app and at
    least one public host name, so a server reachable from a network is never
    also unauthenticated or answering for any name it is given.
    """
    if host not in {"127.0.0.1", "localhost"} and (app.password is None or not public_hosts):
        raise ValueError("a non-loopback bind requires a password and a public host name")
    server = ThreadingHTTPServer((host, port), None)
    bound = server.server_address[1]
    allowed = frozenset({f"127.0.0.1:{bound}", f"localhost:{bound}", *public_hosts})
    server.RequestHandlerClass = make_handler(app, allowed)
    return server


def _basic_matches(header: str, password: str) -> bool:
    """Any user name; the password must match, compared in constant time."""
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    supplied = decoded.partition(":")[2]
    return hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8"))


def _refusal(detail: str, code: str = errors.INVARIANT_VIOLATION) -> dict:
    return {"outcome": "refused", "code": code, "detail": detail}
