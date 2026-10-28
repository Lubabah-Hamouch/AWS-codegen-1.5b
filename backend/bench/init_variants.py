"""Compare init-time mitigations: for each llama-server flag set, time docker run -> /health 200, then the first and
second streamed generation (the first one pays for any lazy weight page-in).

    python bench/init_variants.py IMAGE            (mounts backend/app over /app so main.py edits need no rebuild)

Page cache is warm after the first variant, so these are warm-cache numbers; x86, not Graviton.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from local_bench import PROMPTS, stream  # noqa: E402

VARIANTS = {
    "baseline-1": "",
    "no-repack-1": "--no-repack",
    "baseline-2": "",
    "no-repack-2": "--no-repack",
    "baseline-3": "",
    "ctx1024": "-c 1024",
    "no-repack+ctx1024": "--no-repack -c 1024",
    "no-warmup": "--no-warmup",
    "baseline-4": "",
}
PORT = 9200


def run(image: str, name: str, extra: str) -> dict:
    subprocess.run(["docker", "rm", "-f", "cg-init"], capture_output=True)
    app = str(Path(__file__).resolve().parents[1] / "app")
    t0 = time.monotonic()
    subprocess.run(["docker", "run", "-d", "--name", "cg-init", "--cpus", "2", "--memory", "3g", "-p", f"{PORT}:8080",
                    "-e", "LLAMA_THREADS=2", "-e", f"LLAMA_EXTRA={extra}", "-v", f"{app}:/app:ro", image],
                   check=True, capture_output=True)
    ready = None
    while time.monotonic() - t0 < 200:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                if r.status == 200:
                    ready = round(time.monotonic() - t0, 2)
                    break
        except Exception:
            time.sleep(0.2)
    out = {"variant": name, "flags": extra, "ready_s": ready}
    r1 = stream(PORT, PROMPTS[0])
    r2 = stream(PORT, PROMPTS[1])
    out.update(first_ttft_s=r1["ttft_s"], first_tok_s=r1["decode_tok_s"], second_ttft_s=r2["ttft_s"],
               second_tok_s=r2["decode_tok_s"], ready_plus_first_token_s=round(ready + r1["ttft_s"], 2) if ready else None)
    subprocess.run(["docker", "rm", "-f", "cg-init"], capture_output=True)
    return out


if __name__ == "__main__":
    image = sys.argv[1]
    for n, f in VARIANTS.items():
        print(json.dumps(run(image, n, f)), flush=True)
    print("done")
