"""Step 5: run the format checks and the assert-execution check over generated samples.

A sample passes only if it passes the format checks AND the assertions embedded in its prompt.
Samples whose prompt has no extractable asserts cannot be verified and are failed with
`no_tests_unverifiable`. The assert check runs only on samples that already pass the format checks.

Writes next to the input: <stem>.passed.jsonl, <stem>.failed.jsonl (with `reasons`), and
<stem>.report.json (pass rates, per-reason counts, co-occurrence of failure sets, token stats).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from exec_check import extract_tests, response_code, run_many
from format_checks import check_response, summarize


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("generations")
    args = ap.parse_args()
    src = Path(args.generations)
    base = src.with_suffix("")
    rows = [json.loads(ln) for ln in open(src, encoding="utf-8")]

    fmt_reasons = [check_response(r["response"], r["hit_eos"]) for r in rows]
    tests = [extract_tests(r["instruction"]) for r in rows]

    jobs, job_idx = [], []
    for i, r in enumerate(rows):
        code = response_code(r["response"])
        if not fmt_reasons[i] and tests[i] and code:
            jobs.append((code, tests[i]))
            job_idx.append(i)
    exec_results = dict(zip(job_idx, run_many(jobs)))

    all_reasons = []
    with open(f"{base}.passed.jsonl", "w", encoding="utf-8") as fp, open(f"{base}.failed.jsonl", "w", encoding="utf-8") as ff:
        for i, r in enumerate(rows):
            rs = list(fmt_reasons[i])
            if i in exec_results and not exec_results[i][0]:
                rs.append("test_" + exec_results[i][1])
            if not rs and tests[i] is None:
                rs.append("no_tests_unverifiable")
            all_reasons.append(rs)
            rec = {**r, "reasons": rs, "format_ok": not fmt_reasons[i], "has_tests": tests[i] is not None}
            (ff if rs else fp).write(json.dumps(rec, ensure_ascii=False) + "\n")

    n = max(len(rows), 1)
    fmt_pass = sum(1 for rs in fmt_reasons if not rs)
    summ = summarize(all_reasons)
    summ["format_only_passed"] = fmt_pass
    summ["format_only_pass_rate"] = round(fmt_pass / n, 4)
    summ["samples_with_tests"] = sum(t is not None for t in tests)
    summ["format_ok_and_testable"] = len(jobs)
    summ["format_and_tests_pass_rate"] = round(summ["passed"] / n, 4)
    by_prompt = {}
    for r, rs in zip(rows, all_reasons):
        by_prompt.setdefault(r["id"], []).append(not rs)
    summ["prompts"] = len(by_prompt)
    summ["prompts_with_at_least_one_pass"] = sum(any(v) for v in by_prompt.values())
    summ["failure_sets"] = {" + ".join(k): v for k, v in Counter(tuple(sorted(rs)) for rs in all_reasons if rs).most_common(10)}
    toks = [r["n_tokens"] for r in rows]
    summ["mean_tokens"] = round(sum(toks) / n, 1)
    summ["max_tokens"] = max(toks, default=0)
    Path(f"{base}.report.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
