"""Step 5: run the format checks over generated samples and log why samples fail.

Writes next to the input: <stem>.passed.jsonl, <stem>.failed.jsonl (with `reasons`), and
<stem>.report.json (pass rate, per-reason counts, co-occurrence of failure sets, token stats).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from format_checks import check_response, summarize


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("generations")
    args = ap.parse_args()
    src = Path(args.generations)
    base = src.with_suffix("")
    rows = [json.loads(ln) for ln in open(src, encoding="utf-8")]
    all_reasons = []
    with open(f"{base}.passed.jsonl", "w", encoding="utf-8") as fp, open(f"{base}.failed.jsonl", "w", encoding="utf-8") as ff:
        for r in rows:
            rs = check_response(r["response"], r["hit_eos"])
            all_reasons.append(rs)
            (ff if rs else fp).write(json.dumps({**r, "reasons": rs}, ensure_ascii=False) + "\n")

    summ = summarize(all_reasons)
    by_prompt = {}
    for r, rs in zip(rows, all_reasons):
        by_prompt.setdefault(r["id"], []).append(not rs)
    summ["pass_rate"] = round(summ["passed"] / max(summ["samples"], 1), 4)
    summ["prompts"] = len(by_prompt)
    summ["prompts_with_at_least_one_pass"] = sum(any(v) for v in by_prompt.values())
    summ["failure_sets"] = {" + ".join(k): v for k, v in Counter(tuple(sorted(rs)) for rs in all_reasons if rs).most_common(10)}
    toks = [r["n_tokens"] for r in rows]
    summ["mean_tokens"] = round(sum(toks) / max(len(toks), 1), 1)
    summ["max_tokens"] = max(toks, default=0)
    Path(f"{base}.report.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
