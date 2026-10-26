"""Final contamination check: the actual 4,535 training examples vs the eval benchmarks.

Unlike the pre-generation dedupe (instructions only), this inspects what training will really see:
instruction AND the generated response code, against both the benchmark problem text and the
benchmark reference solutions. Four independent signals:

 1. instruction vs problem text   word-3-gram score = max(Jaccard, containment of the instruction)
                                  (the same measure as prepare_prompts.py)
 2. normalised code equality      training function vs reference function, after dropping docstrings,
                                  annotations and comments and re-printing the AST. Names kept.
 3. word 8-gram overlap           any 8-token window shared between a training example (instruction +
                                  response) and an eval item (problem + reference solution). 8-grams that
                                  occur in more than MAX_TRAIN_DF training examples are boilerplate
                                  (imports, signatures) and are ignored.
 4. entry-point name collisions   training function names equal to a benchmark function name (weak signal:
                                  names such as `add` are generic; listed for manual reading).

Benchmarks: HumanEval, HumanEval+, MBPP (train/validation/test/prompt splits), MBPP+.
"""

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_pipeline"))

from format_checks import extract_blocks  # noqa: E402
from prepare_prompts import best_matches  # noqa: E402

DATA = Path.home() / "work" / "data" / "sft_train.jsonl"
N = 8
MAX_TRAIN_DF = 3
_TOK = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")


def load_eval_items() -> list[dict]:
    from datasets import load_dataset

    items = []
    for repo, cfg, splits in [("openai/openai_humaneval", None, ["test"]), ("evalplus/humanevalplus", None, ["test"]),
                              ("google-research-datasets/mbpp", "full", ["train", "validation", "test", "prompt"]),
                              ("evalplus/mbppplus", None, ["test"])]:
        for sp in splits:
            ds = load_dataset(repo, cfg, split=sp) if cfg else load_dataset(repo, split=sp)
            for r in ds:
                if "humaneval" in repo:
                    problem, code = r["prompt"], r["prompt"] + r["canonical_solution"]
                elif "mbppplus" in repo:
                    problem, code = r["prompt"], r["code"]
                else:
                    problem, code = r["text"], r["code"]
                items.append({"id": f"{repo.split('/')[-1]}:{sp}/{r['task_id']}", "problem": problem, "code": code})
    return items


class _Strip(ast.NodeTransformer):
    """Drop docstrings and annotations so only the logic is compared."""

    def _fn(self, node):
        self.generic_visit(node)
        node.returns = None
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant) \
                and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_arg(self, node):
        node.annotation = None
        return node

    def visit_AnnAssign(self, node):
        return ast.Assign(targets=[node.target], value=node.value or ast.Constant(None), lineno=node.lineno)


def functions(code: str) -> dict[str, str]:
    """name -> normalised source of each top-level / method function in code ({} if it does not parse)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            c = _Strip().visit(ast.parse(ast.unparse(n)))
            out[n.name] = ast.unparse(c)
    return out


def ngrams(text: str) -> set[str]:
    t = _TOK.findall(text.lower())
    return {" ".join(t[i : i + N]) for i in range(len(t) - N + 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(Path.home() / "work" / "eval" / "contamination.json"))
    a = ap.parse_args()

    rows = [json.loads(ln) for ln in open(a.data, encoding="utf-8")]
    train = [{"id": r["id"], "instruction": r["messages"][0]["content"], "response": r["messages"][1]["content"]}
             for r in rows]
    items = load_eval_items()
    print(f"{len(train)} training examples vs {len(items)} eval items", flush=True)

    # 1. instruction vs problem text
    m = best_matches([t["instruction"] for t in train], [{"text": i["problem"]} for i in items])
    sig1 = sorted(({"train_id": t["id"], "score": round(s, 3), "eval": items[j]["id"], "instruction": t["instruction"][:160]}
                   for t, (s, j) in zip(train, m) if j >= 0), key=lambda x: -x["score"])
    thr = {str(x): sum(1 for r in sig1 if r["score"] >= x) for x in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8)}

    # 2. normalised function equality
    ref = defaultdict(list)  # normalised source -> eval ids
    ref_names = defaultdict(set)  # function name -> eval ids
    for i in items:
        for name, src in functions(i["code"]).items():
            ref[src].append(i["id"])
            ref_names[name].add(i["id"])
    sig2, sig4 = [], []
    for t in train:
        blocks = extract_blocks(t["response"])  # responses are fenced; ast needs the bare code
        assert blocks, f"no code block in training example {t['id']}"
        for name, src in functions(blocks[0][1]).items():
            if src in ref and len(src) > 60:  # ignore trivial one-liners
                sig2.append({"train_id": t["id"], "function": name, "matches": ref[src][:3], "chars": len(src)})
            if name in ref_names:
                sig4.append({"train_id": t["id"], "function": name, "eval": sorted(ref_names[name])[:3]})

    # 3. word 8-gram overlap
    train_ng = [ngrams(t["instruction"] + "\n" + t["response"]) for t in train]
    df = Counter(g for s in train_ng for g in s)
    eval_ng = defaultdict(list)
    for i in items:
        for g in ngrams(i["problem"] + "\n" + i["code"]):
            eval_ng[g].append(i["id"])
    sig3 = []
    for t, s in zip(train, train_ng):
        hits = [g for g in s if g in eval_ng and df[g] <= MAX_TRAIN_DF]
        if hits:
            sig3.append({"train_id": t["id"], "shared_8grams": len(hits), "eval": eval_ng[hits[0]][:2], "example": hits[0]})
    sig3.sort(key=lambda x: -x["shared_8grams"])

    by_eval = defaultdict(list)
    for x in sig3:
        by_eval[x["eval"][0]].append((x["shared_8grams"], x["train_id"]))
    sig3_items = sorted(({"eval": k, "train_examples": len(v), "max_shared": max(v)[0], "best_train_id": max(v)[1]}
                         for k, v in by_eval.items()), key=lambda x: -x["max_shared"])
    he_hits = [x for x in sig3_items if "humaneval" in x["eval"]]
    report = {
        "train_examples": len(train), "eval_items": len(items),
        "signal1_instruction_similarity": {"count_at_threshold": thr, "top10": sig1[:10]},
        "signal2_identical_normalised_function": {"count": len(sig2), "examples": sig2[:15]},
        "signal3_shared_8grams": {"examples_with_hits": len(sig3), "top15": sig3[:15],
                                   "eval_items_with_hits": len(sig3_items), "eval_items_hit_ge15": sig3_items[:25],
                                   "humaneval_items_hit_ge8": [x for x in he_hits if x["max_shared"] >= 8]},
        "signal4_name_collisions": {"count": len(sig4),
                                     "most_common_names": Counter(x["function"] for x in sig4).most_common(15)},
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if not isinstance(vv, list)})
                      for k, v in report.items()}, indent=1))
    print("\n== signal1 top:")
    for r in sig1[:6]:
        print(r["score"], r["eval"], "|", r["instruction"][:110].replace("\n", " "))
    print("\n== signal2 (identical function bodies):")
    for r in sig2[:10]:
        print(r)
    print("\n== signal3 top:")
    for r in sig3[:8]:
        print(r["shared_8grams"], r["eval"], "|", r["example"])
    print("\n== signal4 names:", report["signal4_name_collisions"]["most_common_names"])


if __name__ == "__main__":
    main()
