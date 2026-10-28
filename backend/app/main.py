"""Lambda app: llama-server (Q4_K_M GGUF) behind the guardrails, streaming SSE. Runs behind the Lambda Web Adapter.

GET  /health     200 only once the model is loaded (the Web Adapter polls this during init); unguarded
POST /events     non-HTTP invocations (the daily EventBridge warm-up); returns 200
POST /generate   {"prompt": str, "max_tokens": int?}   header x-api-key optional (no key = anonymous tier)
                 -> text/event-stream:  event: token  data: {"t": "<text>"}
                                        event: done   data: {"finish_reason", "tokens", "prompt_tokens", "tok_s", "ttft_s", "prompt_version"}
                                        event: error  data: {"error": "..."}
Errors before streaming starts are plain JSON with an HTTP status (400, 401, 413, 429, 503).
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402
import prompts  # noqa: E402

T0 = time.monotonic()
PORT = int(os.environ.get("PORT", "8080"))
UPSTREAM = "http://127.0.0.1:8081"
THREADS = os.environ.get("LLAMA_THREADS") or str(len(os.sched_getaffinity(0)))
CTX = os.environ.get("LLAMA_CTX", "2048")
DEADLINE_S = float(os.environ.get("GEN_DEADLINE_S", "75"))  # stop before the Lambda timeout
MAX_BODY = 8 * 1024
state = {"ready": False, "model_ready_s": None}


def log(msg: str) -> None:
    print(f"[app +{time.monotonic() - T0:6.2f}s] {msg}", flush=True)


def start_llama() -> None:
    cmd = [os.environ["LLAMA_BIN"], "-m", os.environ["MODEL_PATH"], "--host", "127.0.0.1", "--port", "8081",
           "-t", THREADS, "-c", CTX, "--jinja", "--no-webui", "--parallel", "1",
           *os.environ.get("LLAMA_EXTRA", "").split()]
    log(f"spawn llama-server threads={THREADS} ctx={CTX} extra={os.environ.get('LLAMA_EXTRA', '')!r}")
    proc = subprocess.Popen(cmd, stdout=sys.stderr, stderr=sys.stderr)
    while proc.poll() is None:
        try:
            with urllib.request.urlopen(UPSTREAM + "/health", timeout=1) as r:
                if r.status == 200:
                    state["ready"], state["model_ready_s"] = True, round(time.monotonic() - T0, 2)
                    log("llama-server healthy")
                    return
        except Exception:
            pass
        time.sleep(0.1)
    log(f"llama-server exited rc={proc.returncode}")
    os._exit(1)


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

    def _event(self, name: str, data: dict) -> None:
        b = f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
        self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
        self.wfile.flush()

    def client_ip(self) -> str:
        # Not x-forwarded-for: the Function URL passes a client-supplied one through unchanged (measured), so anyone
        # could pick their own per-IP bucket. The Web Adapter forwards Lambda's own requestContext in this header,
        # replacing any client header of the same name; its sourceIp is the address AWS saw.
        try:
            return json.loads(self.headers.get("x-amzn-request-context", ""))["http"]["sourceIp"]
        except (ValueError, KeyError, TypeError):
            return "unknown"  # every request without a context shares one bucket: strict, never a bypass

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            return self._json(200 if state["ready"] else 503, state)
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] == "/events":
            # Non-HTTP invocations (the daily EventBridge warm-up) arrive here via the Web Adapter. Reaching this line
            # means init ran and the model is loaded; nothing else to do.
            self.rfile.read(min(int(self.headers.get("content-length", 0)), MAX_BODY))
            return self._json(200, {"warm": state["ready"]})
        if self.path.split("?")[0] != "/generate":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("content-length", 0))
            if n > MAX_BODY:
                return self._json(413, {"error": "request too large"})
            req = json.loads(self.rfile.read(n) or b"{}")
            messages = prompts.render_generate(req.get("prompt") if isinstance(req, dict) else None)
            asked = req.get("max_tokens", 512)
            if not isinstance(asked, int) or asked < 1:
                raise prompts.PromptError("max_tokens must be a positive integer")
        except (ValueError, UnicodeDecodeError) as e:  # PromptError and bad JSON are both ValueError
            return self._json(400, {"error": str(e)})
        if not state["ready"]:
            return self._json(503, {"error": "starting"}, {"retry-after": "5"})

        adm = guard.admit(self.headers.get("x-api-key"), self.client_ip())
        if not adm.ok:
            return self._json(adm.status, {"error": adm.message}, {"retry-after": "2"} if adm.status == 429 else None)
        try:
            self.stream(messages, min(asked, adm.max_tokens), adm)
        except (BrokenPipeError, ConnectionResetError):
            log(f"client went away subject={adm.subject}")
        finally:
            guard.release(adm)

    def stream(self, messages: list, max_tokens: int, adm) -> None:
        body = json.dumps({"messages": messages, "stream": True, "stream_options": {"include_usage": True},
                           "max_tokens": max_tokens, "temperature": 0, "top_k": 1, "seed": 42}).encode()
        up_req = urllib.request.Request(UPSTREAM + "/v1/chat/completions", data=body,
                                        headers={"content-type": "application/json"})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()
        t0, ttft, finish, usage, timings = time.monotonic(), None, None, {}, {}
        up = None
        try:
            up = urllib.request.urlopen(up_req, timeout=DEADLINE_S)
            for raw in up:
                line = raw.decode().strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                ev = json.loads(line[5:])
                usage, timings = ev.get("usage") or usage, ev.get("timings") or timings
                for c in ev.get("choices", []):
                    text = (c.get("delta") or {}).get("content")
                    if text:
                        ttft = ttft if ttft is not None else time.monotonic() - t0
                        self._event("token", {"t": text})
                    finish = c.get("finish_reason") or finish
                if time.monotonic() - t0 > DEADLINE_S:
                    finish = "time_limit"
                    break
            up.close()
            # Free the slot before telling the client we are done: a client that sends its next request on `done`
            # must not find its own finished request still holding the slot. (do_POST releases again; that is a no-op.)
            guard.release(adm)
            self._event("done", {"finish_reason": finish, "tokens": usage.get("completion_tokens"),
                                 "prompt_tokens": usage.get("prompt_tokens"),
                                 "tok_s": round(timings["predicted_per_second"], 1) if timings.get("predicted_per_second") else None,
                                 "ttft_s": round(ttft, 2) if ttft is not None else None,
                                 "prompt_version": prompts.VERSION})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            log(f"done subject={adm.subject} tokens={usage.get('completion_tokens')} finish={finish} "
                f"ttft={ttft and round(ttft, 2)} total={time.monotonic() - t0:.2f}s tok_s={timings.get('predicted_per_second')}")
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception as e:  # upstream failure mid-stream: tell the client, never hang
            log(f"stream error: {type(e).__name__}: {e}")
            if up is not None:
                up.close()
            guard.release(adm)
            try:
                self._event("error", {"error": "generation failed"})
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                pass
        finally:
            if up is not None:
                up.close()  # closing the connection makes llama-server abort an unfinished generation


if __name__ == "__main__":
    log("python started")
    threading.Thread(target=start_llama, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
