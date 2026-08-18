#!/usr/bin/env python3
"""
Transparent HTTP Proxy for P2S Trace Recording.

FIX over original: step counters are now per-flow in a thread-safe dict,
not a pair of shared globals. Each shell script injects:
  X-Flow-ID: sf3_auth_flow
so the proxy knows which flow a request belongs to and increments that
flow's counter atomically. Flows reset when a /auth/register POST arrives
on a fresh X-Flow-ID value.
"""

import json
import os
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────
LISTEN_PORT    = 8090                    # proxy listens here
TARGET_HOST    = "http://localhost:8080" # forward to backend (change for Seal: 8080, AITasker: 3001)
OUTPUT_FILE    = "primitive_traces.jsonl"
RESET_PATH     = "/api/auth/register"   # POST to this path resets the flow counter
                                         # AITasker: "/auth/register"
                                         # SealHackathon: "/api/auth/register"

# ── Thread-safe per-flow state ────────────────────────────────────────────────
_lock         = threading.Lock()
_flow_steps   = {}   # {flow_id: step_counter}
_flow_file_lock = threading.Lock()   # separate lock for file writes

def _get_next_step(flow_id: str, is_reset: bool) -> int:
    """Atomically returns the next step number for flow_id."""
    with _lock:
        if is_reset or flow_id not in _flow_steps:
            _flow_steps[flow_id] = 1
        else:
            _flow_steps[flow_id] += 1
        return _flow_steps[flow_id]


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version   = "P2SProxy/2.0"

    # ── Suppress default access log noise ────────────────────────────────────
    def log_message(self, format, *args):
        pass

    def _send_error_response(self, status: int, message: str):
        body = json.dumps({"error": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_request(self, method: str):
        # ── Extract flow identity from header injected by shell scripts ───────
        # Shell scripts must pass: -H "X-Flow-ID: sf3_auth_flow"
        # Fallback: generate a UUID so the proxy still works without the header
        raw_flow_id = self.headers.get("X-Flow-ID", "").strip()
        if not raw_flow_id:
            raw_flow_id = f"flow_{uuid.uuid4().hex[:12]}"

        # Reconstruct full target URL
        path_qs = self.path   # includes query string e.g. /api/teams?trackId=...
        target_url = f"{TARGET_HOST}{path_qs}"

        # Detect whether this request resets the flow step counter
        path_only  = path_qs.split("?")[0]
        is_reset   = (method == "POST" and path_only == RESET_PATH)

        # Assign step number atomically
        step = _get_next_step(raw_flow_id, is_reset)

        if is_reset:
            print(f"\n[PROXY] New flow '{raw_flow_id}' — step counter reset")

        # ── Read request body ─────────────────────────────────────────────────
        content_length = int(self.headers.get("Content-Length", 0))
        req_body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        # ── Build forwarding headers (strip proxy-specific and X-Flow-ID) ─────
        skip_headers = {
            "host", "proxy-connection", "connection",
            "content-length", "x-flow-id",
        }
        forward_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in skip_headers
        }

        # ── Forward to backend ────────────────────────────────────────────────
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.request(
                    method  = method,
                    url     = target_url,
                    headers = forward_headers,
                    content = req_body_bytes,
                )
        except Exception as exc:
            print(f"[PROXY] ✗ Failed to forward {method} {target_url}: {exc}")
            self._send_error_response(502, f"Bad Gateway: {exc}")
            return

        res_body_bytes = response.content

        # ── Stream response back to client ────────────────────────────────────
        self.send_response(response.status_code)
        skip_resp = {"transfer-encoding", "content-length", "connection"}
        for k, v in response.headers.items():
            if k.lower() not in skip_resp:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(res_body_bytes)))
        self.end_headers()
        self.wfile.write(res_body_bytes)

        # ── Log to JSONL ──────────────────────────────────────────────────────
        self._log_transaction(
            flow_id     = raw_flow_id,
            step        = step,
            method      = method,
            path        = path_qs,
            req_headers = dict(self.headers),
            req_body    = req_body_bytes,
            status_code = response.status_code,
            res_body    = res_body_bytes,
        )

    def do_GET(self):    self.do_request("GET")
    def do_POST(self):   self.do_request("POST")
    def do_PUT(self):    self.do_request("PUT")
    def do_PATCH(self):  self.do_request("PATCH")
    def do_DELETE(self): self.do_request("DELETE")

    def _log_transaction(
        self, flow_id, step, method, path,
        req_headers, req_body, status_code, res_body
    ):
        # Skip health check noise
        if path.rstrip("/") in ("/health", "/api/health", "/actuator/health"):
            return

        def _parse(b: bytes):
            if not b:
                return None
            try:
                return json.loads(b.decode("utf-8"))
            except Exception:
                return b.decode("utf-8", errors="ignore")

        # Mask sensitive headers — never store raw tokens in traces
        masked_headers = {}
        for k, v in req_headers.items():
            if k.lower() in ("authorization", "x-sepay-signature", "cookie"):
                masked_headers[k] = f"<{k.upper()}_MASKED>"
            elif k.lower() == "x-flow-id":
                continue   # internal header, not needed in trace
            else:
                masked_headers[k] = v

        trace_step = {
            "flow_id":   flow_id,
            "step":      step,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method":  method,
                "path":    path,
                "headers": masked_headers,
                "body":    _parse(req_body),
            },
            "response": {
                "status_code": status_code,
                "body":        _parse(res_body),
            },
        }

        with _flow_file_lock:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_step, ensure_ascii=False) + "\n")

        print(f"[PROXY] ✓ {flow_id} | step {step:>3} | {method:6} {path[:60]} → {status_code}")


def run_proxy():
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    print("=" * 54)
    print(f" P2S Proxy v2  listening on port {LISTEN_PORT}")
    print(f" Forwarding to : {TARGET_HOST}")
    print(f" Output file   : {os.path.abspath(OUTPUT_FILE)}")
    print(f" Flow reset on : POST {RESET_PATH}")
    print("=" * 54)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[PROXY] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    run_proxy()
