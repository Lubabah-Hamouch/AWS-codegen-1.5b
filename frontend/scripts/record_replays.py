"""Record replays for the playground from the deployed backend: real output, real per-token arrival times.

    python frontend/scripts/record_replays.py [FUNCTION_URL]

Turns the kill switch off for the recording and back ON at exit (whatever happens). Uses the demo API key from
infra/.demo-key so the recordings do not spend the anonymous quota; the key is only sent to the backend, never
written to the output. Writes frontend/public/replays/<id>.json and index.json.
"""

import atexit
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = (sys.argv[1] if len(sys.argv) > 1 else "https://sug6pvql5qkkk3tm7udviuyoc40jwvys.lambda-url.eu-north-1.on.aws").rstrip("/")
KEY = (ROOT / "infra" / ".demo-key").read_text(encoding="utf-8").strip()
OUT = ROOT / "frontend" / "public" / "replays"
SEED = ROOT / "infra" / "scripts" / "seed_state.py"
ENDPOINT = "Lambda arm64 · 3008 MB · 2 threads · eu-north-1"

RUNS = [  # id, chip title, prompt (the playground's example prompts)
    ("fibonacci", "fibonacci", "Write a Python function that returns the nth Fibonacci number."),
    ("palindrome", "is_palindrome", "Write a function that checks whether a string is a palindrome, ignoring case and punctuation."),
    ("merge-intervals", "merge_intervals", "Write a function that merges overlapping intervals in a list of (start, end) tuples."),
    ("roman", "roman_to_int", "Write a function that converts a Roman numeral string to an integer."),
    ("anagrams", "group_anagrams", "Write a function that groups a list of words into anagram groups."),
]


def seed(*a):
    subprocess.run([sys.executable, str(SEED), *a], check=True, capture_output=True)


def record(prompt: str) -> dict:
    req = urllib.request.Request(URL + "/generate", data=json.dumps({"prompt": prompt, "max_tokens": 512}).encode(),
                                 headers={"content-type": "application/json", "x-api-key": KEY})
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000)  # noqa: E731
    tokens, done, name = [], None, None
    with urllib.request.urlopen(req, timeout=120) as r:
        first_byte = ms()
        for raw in r:
            line = raw.decode().rstrip("\r\n")
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                d = json.loads(line[5:])
                if name == "token":
                    tokens.append([d["t"], ms()])
                elif name == "done":
                    done, done_ms = d, ms()
                elif name == "error":
                    raise RuntimeError(d)
    if not done:
        raise RuntimeError("no done event")
    done.pop("remaining", None)  # about the recording key's quota, meaningless to a viewer
    return {"first_byte_ms": first_byte, "tokens": tokens, "done_ms": done_ms, "done": done}


def main():
    atexit.register(lambda: (seed("--kill", "on"), print("kill switch ON")))
    seed("--kill", "off")
    with urllib.request.urlopen(URL + "/health", timeout=150) as r:  # warm up so recordings are not cold starts
        print("health", r.status)
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for rid, title, prompt in RUNS:
        rec = record(prompt)
        rep = {"id": rid, "title": title, "prompt": prompt,
               "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "endpoint": ENDPOINT, **rec}
        (OUT / f"{rid}.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        index.append({"id": rid, "title": title, "prompt": prompt})
        d = rec["done"]
        print(f"{rid}: {d['tokens']} tokens, {d['tok_s']} tok/s, first token {rec['tokens'][0][1]} ms, {d['finish_reason']}")
        time.sleep(1)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
