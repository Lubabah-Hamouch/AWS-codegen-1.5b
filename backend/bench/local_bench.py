"""Time a container locally: docker run -> /health 200 (cold start), then streamed generations (TTFT, tokens/s).

    python bench/local_bench.py IMAGE [--cpus 2] [--memory 3g] [--runs 3] [--threads N]

Runs `docker run` itself so the clock starts at the same point every time. x86 results say nothing about
Graviton speed; they measure container overhead and the init path.
"""

import argparse
import json
import subprocess
import time
import urllib.request

PROMPTS = ["Write a Python function that returns the nth Fibonacci number.",
           "Write a function that checks whether a string is a palindrome, ignoring case and punctuation.",
           "Write a function that merges two sorted lists into one sorted list."]


def stream(port: int, prompt: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/generate",
                                 data=json.dumps({"prompt": prompt, "max_tokens": 512}).encode(),
                                 headers={"content-type": "application/json"})
    t0, first, n, finish, usage = time.monotonic(), None, 0, None, None
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            ev = json.loads(line[5:])
            if ev.get("usage"):
                usage = ev["usage"]
            for c in ev.get("choices", []):
                if c.get("delta", {}).get("content"):
                    first = first or time.monotonic()
                    n += 1
                finish = c.get("finish_reason") or finish
    end = time.monotonic()
    return {"chunks": n, "ttft_s": round(first - t0, 3), "total_s": round(end - t0, 2),
            "decode_tok_s": round((n - 1) / (end - first), 1) if n > 1 else None, "finish": finish,
            "completion_tokens": (usage or {}).get("completion_tokens")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--cpus", default="2")
    ap.add_argument("--memory", default="3g")
    ap.add_argument("--threads", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--port", type=int, default=9000)
    a = ap.parse_args()
    name = "codegen-bench"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    env = ["-e", f"LLAMA_THREADS={a.threads}"] if a.threads else []
    t0 = time.monotonic()
    subprocess.run(["docker", "run", "-d", "--name", name, "--cpus", a.cpus, "--memory", a.memory,
                    "-p", f"{a.port}:8080", *env, a.image], check=True, capture_output=True)
    ready = None
    while time.monotonic() - t0 < 300:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=1) as r:
                if r.status == 200:
                    ready = time.monotonic() - t0
                    break
        except Exception:
            time.sleep(0.2)
    print(json.dumps({"image": a.image, "cpus": a.cpus, "memory": a.memory, "cold_start_to_ready_s": ready and round(ready, 2)}))
    for i in range(a.runs):
        print(json.dumps({"run": i, **stream(a.port, PROMPTS[i % len(PROMPTS)])}))
    mem = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name], capture_output=True, text=True)
    print("mem:", mem.stdout.strip())
    print(subprocess.run(["docker", "logs", name], capture_output=True, text=True).stderr[-1500:] if False else "")
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


if __name__ == "__main__":
    main()
