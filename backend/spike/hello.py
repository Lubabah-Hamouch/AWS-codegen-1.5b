"""Spike 1 app: "hello SSE" behind the real guardrails. No model; it streams numbered events on a timer so we can
see whether a real Function URL delivers them incrementally.

GET  /health            readiness (no guard)
GET|POST /hello?n=20&delay=0.2   guarded SSE stream: n events, `delay` seconds apart, then `event: done`
Auth: optional `x-api-key` header; no key = anonymous tier.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

PORT = int(os.environ.get("PORT", "8080"))
MAX_EVENTS, MAX_SECONDS = 100, 25


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code: int, body: dict, extra: dict | None = None) -> None:
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _chunk(self, data: str) -> None:
        b = data.encode()
        self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
        self.wfile.flush()

    def client_ip(self) -> str:
        # Lambda's front end appends the real client address; take the last entry, not one the client could forge.
        xff = self.headers.get("x-forwarded-for", "")
        return xff.split(",")[-1].strip() or self.client_address[0]

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            return self._json(200, {"ready": True})
        if url.path != "/hello":
            return self._json(404, {"error": "not found"})
        self.hello(parse_qs(url.query))

    do_POST = do_GET

    def hello(self, q: dict) -> None:
        adm = guard.admit(self.headers.get("x-api-key"), self.client_ip())
        if not adm.ok:
            return self._json(adm.status, {"error": adm.message}, {"retry-after": "2"} if adm.status == 429 else None)
        try:
            n = min(int(q.get("n", ["20"])[0]), MAX_EVENTS)
            delay = float(q.get("delay", ["0.2"])[0])
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            t0 = time.monotonic()
            for i in range(n):
                if time.monotonic() - t0 > MAX_SECONDS:
                    break
                self._chunk(f"data: {json.dumps({'i': i, 't': round(time.monotonic() - t0, 2)})}\n\n")
                time.sleep(delay)
            self._chunk(f"event: done\ndata: {json.dumps({'subject': adm.subject, 'events': i + 1})}\n\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            guard.release(adm)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
