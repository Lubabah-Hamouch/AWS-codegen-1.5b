"""Turn filtered generations into the SFT dataset.

Input : <gen>.passed.jsonl (samples that passed the format checks and the prompt's asserts)
Output: sft_train.jsonl, one line per prompt: {"id", "messages": [user, assistant]}.

One passing response is kept per prompt (seeded random choice) so easy prompts do not dominate
and the model sees each task once. The plain user instruction is used with NO system prompt: the
format is meant to be learned into the weights. All passing samples remain in the .passed.jsonl.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from common import SEED


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("passed")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    by_prompt = defaultdict(list)
    for ln in open(args.passed, encoding="utf-8"):
        r = json.loads(ln)
        by_prompt[r["id"]].append(r)

    rng = random.Random(args.seed)
    rows = []
    for pid in sorted(by_prompt):
        r = rng.choice(by_prompt[pid])
        rows.append({"id": pid, "messages": [{"role": "user", "content": r["instruction"]},
                                              {"role": "assistant", "content": r["response"].strip()}]})
    with open(Path(args.out), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"prompts_with_a_pass": len(rows), "passing_samples": sum(len(v) for v in by_prompt.values()), "out": args.out}))


if __name__ == "__main__":
    main()
