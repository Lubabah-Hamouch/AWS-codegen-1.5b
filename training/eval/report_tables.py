"""Print markdown tables for docs/eval_report.md from ~/work/eval/scored_*.json.

    python report_tables.py base_bf16 merged_bf16 gguf_q4km

Columns are the configs given; paired McNemar tests compare consecutive columns.
"""

import json
import sys
from math import comb
from pathlib import Path

OUT = Path.home() / "work" / "eval"
LABEL = {"base_bf16": "base bf16", "base_nf4": "base NF4", "ckpt250": "ckpt-250 NF4 + runtime LoRA",
         "merged_bf16": "**ckpt-250 merged, bf16**", "gguf_q4km": "**ckpt-250 merged, Q4_K_M GGUF**"}


def load(c):
    return json.loads((OUT / f"scored_{c}.json").read_text(encoding="utf-8"))


def mcnemar(a, b, key):
    ra, rb = {r["task_id"]: r[key] for r in a["rows"]}, {r["task_id"]: r[key] for r in b["rows"]}
    w = sum(ra[i] and not rb[i] for i in ra)
    l = sum(rb[i] and not ra[i] for i in ra)
    n, k = w + l, min(w, l)
    p = min(1.0, 2 * sum(comb(n, x) for x in range(k + 1)) / 2**n) if n else 1.0
    return w, l, p


def main(configs):
    data = [load(c) for c in configs]
    S = [d["summary"] for d in data]
    n = S[0]["n_tasks"]
    print("| | " + " | ".join(LABEL[c] for c in configs) + " |")
    print("|---|" + "---|" * len(configs))

    def row(name, f):
        print(f"| {name} | " + " | ".join(f(s) for s in S) + " |")

    cnt = lambda s, k: round(s[k] * n)
    row("HumanEval pass@1", lambda s: f"{s['pass@1_humaneval'] * 100:.1f}% ({cnt(s, 'pass@1_humaneval')}/{n})")
    row("HumanEval+ pass@1", lambda s: f"{s['pass@1_humaneval_plus'] * 100:.1f}% ({cnt(s, 'pass@1_humaneval_plus')}/{n})")
    row("HumanEval, definitions only", lambda s: f"{s['pass@1_humaneval_defs_only'] * 100:.1f}%")
    row("HumanEval+, definitions only", lambda s: f"{s['pass@1_humaneval_plus_defs_only'] * 100:.1f}%")
    row("Format-clean", lambda s: f"{s['format_clean'] * 100:.1f}% ({cnt(s, 'format_clean')}/{n})")
    row("Stopped on its own", lambda s: f"{s['stopped_on_eos'] * 100:.1f}%")
    row("Mean response tokens", lambda s: f"{s['mean_tokens']:.0f}")
    print("\nFormat failures:")
    keys = [k for k in dict.fromkeys(k for s in S for k in s["format_failure_counts"])]
    print("| check | " + " | ".join(configs) + " |")
    print("|---|" + "---|" * len(configs))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(s["format_failure_counts"].get(k, 0)) for s in S) + " |")
    print("\nPaired (consecutive columns, first-only wins / second-only wins / exact McNemar p):")
    for (ca, da), (cb, db) in zip(zip(configs, data), list(zip(configs, data))[1:]):
        for key, nm in (("pass_he", "HumanEval"), ("pass_heplus", "HumanEval+")):
            w, l, p = mcnemar(db, da, key)
            print(f"- {cb} vs {ca}, {nm}: {cb}-only {w}, {ca}-only {l}, p={p:.2f}")
    for c, s in zip(configs, S):
        print(f"- {c}: gen_seconds={s['gen_seconds']}, bs1_agreement={s['bs1_agreement']}")


if __name__ == "__main__":
    main(sys.argv[1:])
