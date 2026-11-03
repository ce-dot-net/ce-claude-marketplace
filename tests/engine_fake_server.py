#!/usr/bin/env python3
"""Localhost fake ACE server for the engine tests (DESIGN §14; adapted from m3 fake_server.py).

Logs every request (method, path, headers with Authorization masked, JSON body) as one
JSON line to the log file. Answers /api/v1/config, /patterns/search, /traces,
/traces/stream and /api/v1/auth/refresh like the real server. FAKE_MODE=401|500 makes
the trace POSTs fail; FAKE_REFRESH=429|reuse fails the token refresh; FAKE_SEARCH=401 rejects searches; FAKE_GRAPH_DELAY=<s> stalls the graph edge refresh;
FAKE_STATUS=401|403|404|500 fails GET /analytics (ace-cli status);
FAKE_TRACE_502=<n> answers the first n trace POSTs 502 with Retry-After: 0 (the SDK retries at once). Usage: engine_fake_server.py <port|0> <log> [<portfile>]
(port 0 = pick a free port and write it to <portfile>).
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = os.environ.get("FAKE_MODE", "ok")
LOG = sys.argv[2]
_502 = {"left": int(os.environ.get("FAKE_TRACE_502") or 0), "lock": threading.Lock()}

PATTERN = {"id": "ctx-fake-0001", "content": "use jq -n --arg for hook JSON", "section": "strategies",
           "domain": "hooks", "confidence": 0.9, "helpful": 3, "harmful": 0,
           "cumulative_v15_reward": 1.0, "isAtRisk": False, "n_hot_pos": 1, "n_hot_neg": 0,
           "match_factors": {"bandit_rank": 1, "retrieval_log_id": 7, "semantic_score": 0.8}}
SEARCH = {"similar_patterns": [PATTERN], "count": 1, "threshold": 0.5, "retrieval_id": "ret-fake-1",
          "feedback_downvote": True, "render_full_pct": 0,
          "domains_summary": {"hooks": 1}}
TRACE_OK = {"stored": True, "analysis_performed": True, "learning_queued": True, "trace_id": "fake-trace-1",
            "learning_statistics": {"patterns_created": 1, "patterns_updated": 2}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _log(self, body):
        h = {k: ("Bearer ***" if k.lower() == "authorization" else v) for k, v in self.headers.items()}
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = body
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": time.time(), "method": self.command, "path": self.path,
                                "headers": h, "body": parsed}) + "\n")

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-ACE-Token-Expires-In", "172800")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._log(None)
        if self.path.startswith("/analytics"):  # `ace-cli status` (8.1.0 context verify): FAKE_STATUS=ok|401|403|404|500
            st = os.environ.get("FAKE_STATUS", "ok")
            if st != "ok":
                msg = {"401": "token expired", "403": "no access to project", "404": "project not found"}.get(st, "boom")
                return self._send(int(st), {"detail": msg, "message": msg})
            return self._send(200, {"total_patterns": 1, "by_section": {"strategies_and_hard_rules": 1}, "by_domain": {"hooks": 1}})
        if "graph" in self.path:
            time.sleep(float(os.environ.get("FAKE_GRAPH_DELAY", "0")))
            return self._send(200, {"edges": [], "patterns": []})
        if self.path.startswith("/api/v1/config"):
            return self._send(200, {"search_threshold": 0.5, "search_top_k": 100,
                                    "runtime_settings": {"learningEnabled": True,
                                                         "patternDefaultSection": "general"}})
        self._send(404, {"message": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        self._log(body)
        if self.path.startswith("/traces"):
            if MODE == "401":
                b = json.dumps({"message": "token expired"}).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-ACE-Token-Expired", "true")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if MODE == "500":
                return self._send(500, {"message": "boom"})
            with _502["lock"]:
                gateway = _502["left"] > 0
                _502["left"] -= gateway
            if gateway:  # a restarting server behind the gateway
                b = b"<html>502 Bad Gateway</html>"
                self.send_response(502)
                self.send_header("Retry-After", "0")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            return self._send(200, TRACE_OK)
        if self.path.startswith("/patterns/search"):
            if os.environ.get("FAKE_SEARCH") == "401":  # the token family was revoked server-side
                return self._send(401, {"detail": "token revoked"})
            return self._send(200, SEARCH)
        if self.path.startswith("/api/v1/auth/refresh"):
            refresh = os.environ.get("FAKE_REFRESH", "ok")
            if refresh == "429":  # 30 req/min per IP on the refresh endpoint
                return self._send(429, {"detail": "rate limited"})
            if refresh == "reuse":  # a rotated token presented after the 60 s grace revokes the family
                return self._send(400, {"error": "invalid_grant", "reason": "reuse"})
            return self._send(200, {"access_token": "ace_user_FAKEREFRESHED_0001", "refresh_token": "rfk_FAKE_NEW",
                                    "expires_in": 172800, "refresh_expires_in": 2592000})
        self._send(404, {"message": "nope"})


ThreadingHTTPServer.request_queue_size = 128  # default 5 overflows when a loaded host connects in bursts
srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H)
if len(sys.argv) > 3:
    with open(sys.argv[3] + ".tmp", "w") as f:  # atomic: the reader never sees a half-written port
        f.write(str(srv.server_address[1]))
    os.replace(sys.argv[3] + ".tmp", sys.argv[3])
srv.serve_forever()
