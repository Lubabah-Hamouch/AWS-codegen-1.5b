"""Steps 1-2: extract instruction prompts and remove overlap with the evaluation sets.

Method: lexical near-duplicate detection. Texts are lower-cased and tokenized to
alphanumeric words; each is reduced to its set of word 3-grams ("shingles"). For each training
prompt P and each eval text E we compute

    score = max(Jaccard(P, E), |P ∩ E| / |P|)

The second term (containment of the prompt inside the eval text) catches a short instruction
copied out of a long HumanEval docstring, which Jaccard alone would miss. A prompt is dropped
if its best score against any eval text is >= --threshold. Counts at several thresholds and the
closest matches are written to the report so the cut-off can be judged, not just trusted.

Limit: this catches copying and light rewording, NOT paraphrase. A semantic (embedding) pass
could be added later if needed.
"""

import argparse
import json
import re
from collections import Counter, defaultdict

from common import SEED, SOURCE_DATASET, ensure_data_dir
from datasets import load_dataset
from exec_check import extract_tests

# (repo, config, splits, text field)
EVAL_SOURCES = [
    ("openai/openai_humaneval", None, ["test"], "prompt"),
    ("evalplus/humanevalplus", None, ["test"], "prompt"),
    ("google-research-datasets/mbpp", "full", ["train", "validation", "test", "prompt"], "text"),
    ("evalplus/mbppplus", None, ["test"], "prompt"),
]
THRESHOLDS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
_TOKEN = re.compile(r"[a-z0-9]+")


def shingles(text: str, n: int = 3) -> frozenset:
    toks = _TOKEN.findall(text.lower())
    if len(toks) < n:
        return frozenset([" ".join(toks)]) if toks else frozenset()
    return frozenset(" ".join(toks[i : i + n]) for i in range(len(toks) - n + 1))


def load_eval_texts() -> list[dict]:
    items = []
    for repo, config, splits, field in EVAL_SOURCES:
        for split in splits:
            ds = load_dataset(repo, config, split=split) if config else load_dataset(repo, split=split)
            for row in ds:
                items.append({"source": f"{repo}:{split}", "task_id": str(row["task_id"]), "text": row[field]})
    return items


def best_matches(prompts: list[str], evals: list[dict]) -> list[tuple[float, int]]:
    """For each prompt return (best_score, index_of_best_eval_item)."""
    eval_sh = [shingles(e["text"]) for e in evals]
    index = defaultdict(list)
    for i, sh in enumerate(eval_sh):
        for s in sh:
            index[s].append(i)
    out = []
    for p in prompts:
        psh = shingles(p)
        if not psh:
            out.append((0.0, -1))
            continue
        shared = Counter()
        for s in psh:
            for i in index.get(s, ()):
                shared[i] += 1
        best = (0.0, -1)
        for i, inter in shared.items():
            union = len(psh) + len(eval_sh[i]) - inter
            score = max(inter / union, inter / len(psh))
            if score > best[0]:
                best = (score, i)
        out.append(best)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.3)
    args = ap.parse_args()
    out_dir = ensure_data_dir()

    ds = load_dataset(SOURCE_DATASET, split="train")
    print(f"source rows: {len(ds)}")
    rows = [{"id": int(r["id"]), "instruction": r["instruction"].strip()} for r in ds]
    empties = sum(1 for r in rows if not r["instruction"])
    exact_dupes = len(rows) - len({r["instruction"] for r in rows})
    seen, uniq = set(), []
    for r in rows:
        if r["instruction"] and r["instruction"] not in seen:
            seen.add(r["instruction"])
            uniq.append(r)

    evals = load_eval_texts()
    print(f"eval texts: {len(evals)}")
    matches = best_matches([r["instruction"] for r in uniq], evals)

    at_threshold = {str(t): sum(1 for s, _ in matches if s >= t) for t in THRESHOLDS}
    kept, removed = [], []
    for r, (score, i) in zip(uniq, matches):
        if score >= args.threshold:
            removed.append({**r, "score": round(score, 3), "matched": evals[i]["source"] + "/" + evals[i]["task_id"]})
        else:
            kept.append(r)

    with open(out_dir / "prompts.jsonl", "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Prompts with an embedded assert block can be verified by execution; generation samples from these.
    with_tests = [r for r in kept if extract_tests(r["instruction"])]
    with open(out_dir / "prompts_with_tests.jsonl", "w", encoding="utf-8") as f:
        for r in with_tests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    top = sorted(removed, key=lambda x: -x["score"])
    near_miss = sorted(
        (
            {**r, "score": round(s, 3), "matched": evals[i]["source"] + "/" + evals[i]["task_id"]}
            for r, (s, i) in zip(uniq, matches)
            if args.threshold - 0.15 <= s < args.threshold
        ),
        key=lambda x: -x["score"],
    )
    report = {
        "source": SOURCE_DATASET,
        "source_rows": len(ds),
        "empty": empties,
        "exact_duplicate_instructions": exact_dupes,
        "after_exact_dedupe": len(uniq),
        "eval_texts": len(evals),
        "method": "word 3-gram shingles; score=max(jaccard, containment_of_prompt)",
        "threshold": args.threshold,
        "removed_at_each_threshold": at_threshold,
        "removed": len(removed),
        "kept": len(kept),
        "kept_with_extractable_asserts": len(with_tests),
        "seed": SEED,
        "closest_removed": top[:8],
        "closest_kept": near_miss[:8],
    }
    (out_dir / "dedupe_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if not k.startswith("closest")}, indent=2))


if __name__ == "__main__":
    main()
