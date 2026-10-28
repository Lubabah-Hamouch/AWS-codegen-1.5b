"""Spike app: start llama-server, report readiness, proxy one completion. Replaced by the real app later.

GET  /health    200 only once the model is loaded (the Web Adapter polls this during init)
POST /generate  {"prompt": str, "max_tokens": int} -> streams the upstream SSE through unchanged
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

T0 = time.monotonic()
PORT = int(os.environ.get("PORT", "8080"))
UPSTREAM = "http://127.0.0.1:8081"
THREADS = os.environ.get("LLAMA_THREADS") or str(len(os.sched_getaffinity(0)))
state = {"ready": False, "model_ready_s": None}


def log(msg: str) -> None:
    print(f"[app +{time.monotonic() - T0:6.2f}s] {msg}", flush=True)


def start_llama() -> None:
    cmd = [os.environ["LLAMA_BIN"], "-m", os.environ["MODEL_PATH"], "--host", "127.0.0.1", "--port", "8081",
           "-t", THREADS, "-c", "2048", "--jinja", "--no-webui", "--parallel", "1",
           *os.environ.get("LLAMA_EXTRA", "").split()]  # later flags win, so LLAMA_EXTRA can override -c
    log(f"spawn llama-server threads={THREADS}")
    proc = subprocess.Popen(cmd, stdout=sys.stderr, stderr=sys.stderr)
    while proc.poll() is None:
        try:
            with urllib.request.urlopen(UPSTREAM + "/health", timeout=1) as r:
                if r.status == 200:
                    state["ready"] = True
                    state["model_ready_s"] = round(time.monotonic() - T0, 2)
                    log("llama-server healthy")
                    break
        except Exception:
            pass
        time.sleep(0.1)
    if proc.poll() is not None:
        log(f"llama-server exited rc={proc.returncode}")
        os._exit(1)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: dict) -> None:
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/health":
            self._send(200 if state["ready"] else 503, state)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/generate" or not state["ready"]:
            return self._send(404 if self.path != "/generate" else 503, {"error": "unavailable"})
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        body = json.dumps({"messages": [{"role": "user", "content": req["prompt"]}], "stream": True,
                           "max_tokens": min(int(req.get("max_tokens", 512)), 512),
                           "temperature": 0, "top_k": 1}).encode()
        up = urllib.request.Request(UPSTREAM + "/v1/chat/completions", data=body,
                                    headers={"content-type": "application/json"})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        with urllib.request.urlopen(up) as r:
            for line in r:
                self.wfile.write(line)
                self.wfile.flush()


if __name__ == "__main__":
    log("python started")
    threading.Thread(target=start_llama, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
