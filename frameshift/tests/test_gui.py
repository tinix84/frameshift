#!/usr/bin/env python3
"""Tests for the manual GUI's HTTP boundary (ADR-0022, ADR-0023).

A real server on an ephemeral loopback port, driven with the standard library's
HTTP client. The coordinator underneath is the real one over a temporary store,
so these test the boundary's translation and refusals, not a stub.
"""

from __future__ import annotations

import base64
import contextlib
import http.client
import io
import itertools
import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frameshift.bootstrap import gui_main, gui_vocabulary, manual_coordinator  # noqa: E402
from frameshift.export.decision_record import render  # noqa: E402
from frameshift.gui.server import ManualApp, serve  # noqa: E402

OWNER = {"id": "user_lead_eng", "kind": "human", "role": "decision_owner"}


class GuiBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        counter = itertools.count(1)
        coordinator = manual_coordinator(
            Path(cls._dir.name),
            OWNER,
            clock=lambda: "2026-10-06T09:00:00Z",
            new_suffix=lambda: f"g{next(counter):04d}",
        )
        cls.app = ManualApp(coordinator, token="test-token-0123456789", vocabulary=gui_vocabulary(), record=render)
        cls.server = serve(cls.app, port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._dir.cleanup()

    def call(self, method: str, path: str, body=None, *, token: str | None = "test-token-0123456789", host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json", "Host": host or f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-FrameShift-Token"] = token
        connection.request(method, path, None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        content_type = response.getheader("Content-Type", "")
        return response.status, json.loads(raw) if "json" in content_type else raw.decode("utf-8")

    def open(self, request: str = "Select a 5 kW DC/DC converter.") -> str:
        status, view = self.call("POST", "/api/sessions", {"request": request})
        self.assertEqual(status, 200)
        return view["state"]["id"]

    # ------------------------------------------------------------ the boundary

    def test_the_page_embeds_the_launch_token(self) -> None:
        status, page = self.call("GET", "/", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(re.search(r'const TOKEN = "([^"]+)"', page).group(1), self.app.token)

    def test_an_api_call_without_the_token_is_refused(self) -> None:
        self.assertEqual(self.call("GET", "/api/sessions", token=None)[0], 403)
        self.assertEqual(self.call("GET", "/api/sessions", token="guess")[0], 403)

    def test_a_foreign_host_header_is_refused(self) -> None:
        self.assertEqual(self.call("GET", "/api/sessions", host=f"attacker.example:{self.port}")[0], 421)

    def test_meta_says_no_model_is_connected(self) -> None:
        status, meta = self.call("GET", "/api/meta")
        self.assertEqual((status, meta["model_connected"], meta["operator"]), (200, False, OWNER))

    def test_a_body_that_is_not_an_object_is_a_bad_request(self) -> None:
        self.assertEqual(self.call("POST", "/api/sessions", ["not", "an", "object"])[0], 400)

    # ---------------------------------------------------------- translation

    def test_a_revision_conflict_maps_to_409_with_its_code(self) -> None:
        sid = self.open()
        status, body = self.call(
            "POST", f"/api/sessions/{sid}/statements",
            {"text": "An outcome.", "primary_role": "outcome", "expected_revision": 7},
        )
        self.assertEqual((status, body["code"]), (409, "revision_conflict"))

    def test_intake_is_sealed_through_the_http_confirmation_round_trip(self) -> None:
        sid = self.open()
        _, built = self.call(
            "POST", f"/api/sessions/{sid}/manual-result",
            {"classifications": [{"statement_id": "stmt_001", "primary_role": "proposal"}]},
        )
        status, admitted = self.call("POST", f"/api/sessions/{sid}/engine-result", {"result": built["result"]})
        self.assertEqual((status, admitted["outcome"]), (200, "admitted"))

        _, prepared = self.call("POST", f"/api/sessions/{sid}/gates", {"gate": "intake_correction", "target_id": "stmt_001"})
        request = prepared["confirmation_request"]
        forged = {"request_id": request["id"], "request_digest": "sha256:" + "0" * 64,
                  "status": "submitted", "disposition": "approved", "edited_proposal": None}
        status, refused = self.call("POST", f"/api/confirmations/{request['id']}", {"response": forged})
        self.assertEqual((status, refused["code"]), (409, "approval_stale"))

        _, prepared = self.call("POST", f"/api/sessions/{sid}/gates", {"gate": "intake_correction", "target_id": "stmt_001"})
        request = prepared["confirmation_request"]
        answer = dict(forged, request_id=request["id"], request_digest=request["request_digest"])
        status, sealed = self.call("POST", f"/api/confirmations/{request['id']}", {"response": answer})
        self.assertEqual((status, sealed["phase"]), (200, "framing"))

        _, record = self.call("GET", f"/api/sessions/{sid}/record")
        self.assertIn("approved", record["markdown"])

    def test_a_cancelled_request_cannot_be_answered(self) -> None:
        sid = self.open()
        _, built = self.call("POST", f"/api/sessions/{sid}/manual-result",
                             {"classifications": [{"statement_id": "stmt_001", "primary_role": "need"}]})
        self.call("POST", f"/api/sessions/{sid}/engine-result", {"result": built["result"]})
        _, prepared = self.call("POST", f"/api/sessions/{sid}/gates", {"gate": "intake_correction", "target_id": "stmt_001"})
        request = prepared["confirmation_request"]
        self.assertEqual(self.call("DELETE", f"/api/confirmations/{request['id']}")[0], 200)
        answer = {"request_id": request["id"], "request_digest": request["request_digest"],
                  "status": "submitted", "disposition": "approved", "edited_proposal": None}
        status, body = self.call("POST", f"/api/confirmations/{request['id']}", {"response": answer})
        self.assertEqual((status, body["code"]), (409, "approval_stale"))


class HostedMode(unittest.TestCase):
    """ADR-0023: a network bind is never unauthenticated."""

    PASSWORD = "correct horse battery staple"
    PUBLIC = "frameshift-test.up.railway.app"

    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        coordinator = manual_coordinator(Path(cls._dir.name), OWNER, public_hosts=(cls.PUBLIC,), bind="0.0.0.0")
        cls.app = ManualApp(coordinator, token="hosted-token-0123456789", vocabulary=gui_vocabulary(),
                            record=render, password=cls.PASSWORD)
        cls.server = serve(cls.app, port=0, host="0.0.0.0", public_hosts=(cls.PUBLIC, f"{cls.PUBLIC}:443"))
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._dir.cleanup()

    def get(self, path: str, *, password: str | None = None, host: str | None = None, token: bool = True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or self.PUBLIC}
        if password is not None:
            headers["Authorization"] = "Basic " + base64.b64encode(f"me:{password}".encode()).decode()
        if token:
            headers["X-FrameShift-Token"] = self.app.token
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        response.read()
        connection.close()
        return response.status, response.getheader("WWW-Authenticate")

    def test_the_page_itself_needs_the_password(self) -> None:
        status, challenge = self.get("/", token=False)
        self.assertEqual(status, 401)
        self.assertIn("Basic", challenge)
        self.assertEqual(self.get("/", password=self.PASSWORD, token=False)[0], 200)

    def test_a_wrong_password_is_refused(self) -> None:
        self.assertEqual(self.get("/api/sessions", password="nope")[0], 401)

    def test_the_password_alone_does_not_open_the_api(self) -> None:
        """Basic credentials ride along on cross-site requests; the token does not."""
        self.assertEqual(self.get("/api/sessions", password=self.PASSWORD, token=False)[0], 403)
        self.assertEqual(self.get("/api/sessions", password=self.PASSWORD)[0], 200)

    def test_only_the_public_host_is_served(self) -> None:
        self.assertEqual(self.get("/api/sessions", password=self.PASSWORD, host="evil.example")[0], 421)

    def test_a_network_bind_without_a_password_will_not_start(self) -> None:
        bare = ManualApp(self.app.coordinator, token="t" * 20, vocabulary={}, record=render)
        with self.assertRaises(ValueError):
            serve(bare, port=0, host="0.0.0.0", public_hosts=(self.PUBLIC,))

    def test_hosted_launch_refuses_a_short_password_or_no_host(self) -> None:
        for env in ({"FRAMESHIFT_PASSWORD": "short", "RAILWAY_PUBLIC_DOMAIN": self.PUBLIC},
                    {"FRAMESHIFT_PASSWORD": self.PASSWORD}):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                gui_main(["--hosted", "--store", self._dir.name], environ=env)


if __name__ == "__main__":
    unittest.main()
