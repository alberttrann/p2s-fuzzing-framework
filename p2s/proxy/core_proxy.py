"""
P2S Transparent Proxy: Captures HTTP traffic into primitive traces.
Supports pluggable Flow Separation Strategies.
"""
import json
import uuid
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx

class FlowStrategy:
    def determine_flow_and_step(self, method: str, path: str, headers: dict) -> tuple[str, int]:
        pass

class HeaderFlowStrategy(FlowStrategy):
    """Flows are dictated by a custom X-Flow-ID header injected by test scripts (SEAL mode)."""
    def __init__(self):
        self.lock = threading.Lock()
        self.flow_steps = {}

    def determine_flow_and_step(self, method: str, path: str, headers: dict):
        raw_flow_id = headers.get("X-Flow-ID", f"flow_{uuid.uuid4().hex[:12]}").strip()
        if not raw_flow_id: raw_flow_id = f"flow_{uuid.uuid4().hex[:12]}"
        path_only = path.split("?")[0]
        is_reset = (method == "POST" and path_only.endswith("/auth/register"))
        with self.lock:
            if is_reset or raw_flow_id not in self.flow_steps:
                self.flow_steps[raw_flow_id] = 1
            else:
                self.flow_steps[raw_flow_id] += 1
            return raw_flow_id, self.flow_steps[raw_flow_id]

class EndpointResetStrategy(FlowStrategy):
    """A global flow resets whenever a configured endpoint is hit (AITasker mode)."""
    def __init__(self, reset_endpoint: str):
        self.reset_endpoint = reset_endpoint
        self.lock = threading.Lock()
        self.current_flow_id = f"flow_{uuid.uuid4().hex[:12]}"
        self.step_counter = 0

    def determine_flow_and_step(self, method: str, path: str, headers: dict):
        with self.lock:
            path_only = path.split("?")[0]
            is_reset = (method.upper() == "POST" and path_only.endswith(self.reset_endpoint))
            if is_reset:
                self.current_flow_id = (
                    f"flow_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
                )
                self.step_counter = 1
            else:
                self.step_counter += 1
            return self.current_flow_id, self.step_counter

class P2SProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args): pass

    def do_request(self, method: str):
        target_url = f"{self.server.target_host}{self.path}"
        flow_id, step = self.server.strategy.determine_flow_and_step(
            method, self.path, dict(self.headers)
        )

        content_length = int(self.headers.get("Content-Length", 0))
        req_body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        skip_headers = {"host", "proxy-connection", "connection", "content-length", "x-flow-id"}
        forward_headers = {k: v for k, v in self.headers.items() if k.lower() not in skip_headers}

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.request(
                    method=method, url=target_url,
                    headers=forward_headers, content=req_body_bytes
                )
        except Exception as exc:
            self.send_error(502, f"Bad Gateway: {exc}")
            return

        res_body_bytes = response.content
        self.send_response(response.status_code)
        for k, v in response.headers.items():
            if k.lower() not in {"transfer-encoding", "content-length", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(res_body_bytes)))
        self.end_headers()
        self.wfile.write(res_body_bytes)

        self._log_transaction(
            flow_id, step, method, self.path, dict(self.headers),
            req_body_bytes, response.status_code, res_body_bytes
        )

    def do_GET(self): self.do_request("GET")
    def do_POST(self): self.do_request("POST")
    def do_PUT(self): self.do_request("PUT")
    def do_PATCH(self): self.do_request("PATCH")
    def do_DELETE(self): self.do_request("DELETE")

    def _log_transaction(self, flow_id, step, method, path, req_headers,
                          req_body, status_code, res_body):
        if path.rstrip("/") in ("/health", "/api/health", "/actuator/health"): return

        def _parse(b: bytes):
            if not b: return None
            try: return json.loads(b.decode("utf-8"))
            except Exception: return b.decode("utf-8", errors="ignore")

        masked_headers = {}
        for k, v in req_headers.items():
            if k.lower() == "x-flow-id":
                continue
            if self.server.mask_sensitive_headers and k.lower() in (
                "authorization", "x-sepay-signature", "cookie"
            ):
                masked_headers[k] = f"<{k.upper()}_MASKED>"
            else:
                masked_headers[k] = v

        trace_step = {
            "flow_id": flow_id, "step": step,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method": method, "path": path,
                "headers": masked_headers, "body": _parse(req_body)
            },
            "response": {"status_code": status_code, "body": _parse(res_body)}
        }

        with self.server.file_lock:
            with open(self.server.output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_step, ensure_ascii=False) + "\n")
        print(f"[PROXY] ✓ {flow_id} | step {step:>3} | {method:6} {path[:60]} → {status_code}")

class P2SProxyServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, target_host, strategy, output_file,
                 *, mask_sensitive_headers: bool = True):
        super().__init__(server_address, RequestHandlerClass)
        self.target_host = target_host.rstrip("/")
        self.strategy = strategy
        self.output_file = output_file
        self.mask_sensitive_headers = bool(mask_sensitive_headers)
        self.file_lock = threading.Lock()
