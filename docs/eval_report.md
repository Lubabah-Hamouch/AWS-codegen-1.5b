# Evaluation report: format fine-tune of Qwen2.5-Coder-1.5B-Instruct

Model under test: QLoRA adapter, **checkpoint-250** (step 250 of 273 in epoch 1, i.e. 0.91 epochs; lowest validation loss), on
Qwen2.5-Coder-1.5B-Instruct. Benchmarks: HumanEval and HumanEval+ (164 tasks each), pass@1.

## Summary

- **Format compliance went from 0.6–5.5% to 99.4%.** All but one fine-tuned response is one fenced block with
  docstrings and full type hints that import every name they use, and every one stops on its own. The exception,
  HumanEval/136, uses `Optional` in a type hint without importing it.
- **Correctness did not change measurably.** Against the same-precision (bf16) base: HumanEval 65.2% → 65.9%,
  HumanEval+ 59.1% → 61.6%. Task-level flips are 18 gained vs 17 lost (exact McNemar p = 1.0).
- **No regression**, which is what a format-adaptation fine-tune should show. The 4-bit base scores lower
  (59.1%) than the bf16 base; the adapter brings the 4-bit model back to bf16 level. See "What this does and
  doesn't show" before reading anything into the +6.8 points over the 4-bit base.

> **Changed 2026-10-28: format-clean figures re-scored.** The format check gained a rule: every name used in a type
> hint must be imported or defined (see "Failure analysis" below). HumanEval/136's answer uses `Optional` without
> importing it, which raises a NameError when the function is defined; the old check passed it. Re-scoring the saved
> answers with the extended check moves checkpoint-250 from 100% to 99.4% (163/164) and the shipped Q4_K_M GGUF from
> 99.4% to **98.8% (162/164)**. Base and merged runs have no such answers and are unchanged; pass@1 is unchanged
> everywhere (the tests were re-run). The site, README and model card show the new figures.

## Results

All three runs use the same chat template, the same user message
(`Complete the following Python function:` + the HumanEval prompt) and **no format system prompt**, greedy
decoding, max 768 new tokens, seed 42.

| | base bf16 (reference) | base NF4 4-bit | **checkpoint-250** (NF4 + LoRA) |
|---|---|---|---|
| HumanEval pass@1 | 65.2% (107/164) | 59.1% (97/164) | **65.9%** (108/164) |
| HumanEval+ pass@1 | 59.1% (97/164) | 54.3% (89/164) | **61.6%** (101/164) |
| HumanEval pass@1, definitions only* | 66.5% | 59.8% | 65.9% |
| HumanEval+ pass@1, definitions only* | 61.0% | 54.9% | 61.6% |
| Format-clean responses | 5.5% (9/164) | 0.6% (1/164) | **99.4%** (163/164) |
| Stopped on its own (EOS) | 99.4% | 99.4% | 100% |
| Mean response length (tokens) | 300 | 364 | 164 |

\*Only imports, function/class definitions and constants are executed; module-level example calls, prints
and `__main__` blocks are dropped. This separates "is the function right" from "did the model add extra
top-level code that can crash". It changes the base models by at most 1.9 points and the fine-tune not at all, so the headline
comparison is not an artefact of that.

**Format failures** (a response can have several; "format-clean" means none of them):

| Check | base bf16 | base NF4 | checkpoint-250 |
|---|---|---|---|
| Prose after the code block | 154 | 162 | 0 |
| Prose before the code block | 53 | 122 | 0 |
| Missing return type hint | 115 | 119 | 0 |
| Missing parameter type hint | 104 | 103 | 0 |
| Missing docstring | 98 | 117 | 0 |
| Type-hint name not imported | 0 | 0 | 1 |
| Multiple code blocks / truncated / other | 1 | 8 | 0 |

**Format × correctness (HumanEval)**

| | format OK, passes | format OK, fails | format bad, passes | format bad, fails |
|---|---|---|---|---|
| base bf16 | 9 | 0 | 98 | 57 |
| base NF4 | 1 | 0 | 96 | 67 |
| checkpoint-250 | 108 | 55 | 0 | 1 |

The base model is usually correct but almost never in the target format; the fine-tuned model is in format on all
but one task, and as correct as the base.

**Paired comparison** (checkpoint-250 vs base, per task)

| vs | benchmark | tasks only the fine-tune passes | tasks only the base passes | exact McNemar p |
|---|---|---|---|---|
| base bf16 | HumanEval | 18 | 17 | 1.00 |
| base bf16 | HumanEval+ | 19 | 15 | 0.61 |
| base NF4 | HumanEval | 25 | 14 | 0.11 |
| base NF4 | HumanEval+ | 25 | 13 | 0.07 |

With 164 tasks the 95% interval on one pass@1 figure is about ±7 points.

## Exported model: merged bf16 and Q4_K_M GGUF

The adapter was trained on top of NF4 weights but is shipped merged into the **bf16** base, then quantised
to **Q4_K_M** (llama.cpp b11856, 986 MB; 3.09 GB as f16). The merge was checked by comparing next-token
logits with and without the merged adapter on 3 prompts (same top-1, top-5 overlap 5/5, max logit
difference 0.22–0.25). The table above is not the shipped model (NF4 + runtime adapter); these three are
directly comparable. Same prompts, greedy, max 768 new tokens, seed 42. The GGUF was served with
`llama-server` on CPU (12 threads, 4 parallel slots, `--jinja`); its chat template was checked against the
HF template for the first 20 tasks (0 mismatches).

| | base bf16 | **ckpt-250 merged, bf16** | **ckpt-250 merged, Q4_K_M GGUF** |
|---|---|---|---|
| HumanEval pass@1 | 65.2% (107/164) | **70.1%** (115/164) | 64.0% (105/164) |
| HumanEval+ pass@1 | 59.1% (97/164) | **66.5%** (109/164) | 61.0% (100/164) |
| HumanEval, definitions only | 66.5% | 70.1% | 64.0% |
| HumanEval+, definitions only | 61.0% | 66.5% | 61.0% |
| Format-clean | 5.5% (9/164) | 100% (164/164) | 98.8% (162/164) |
| Stopped on its own | 99.4% | 100% | 100% |
| Mean response tokens | 300 | 167 | 167 |

The two GGUF format failures are a missing return type hint and HumanEval/136's unimported `Optional`; all other
checks pass.

| Paired comparison (per task) | only the first passes | only the second passes | exact McNemar p |
|---|---|---|---|
| merged bf16 vs base bf16, HumanEval | 23 | 15 | 0.26 |
| merged bf16 vs base bf16, HumanEval+ | 26 | 14 | 0.08 |
| Q4_K_M vs merged bf16, HumanEval | 12 (Q4_K_M) | 22 (bf16) | 0.12 |
| Q4_K_M vs merged bf16, HumanEval+ | 13 (Q4_K_M) | 22 (bf16) | 0.18 |

Reading it:
- **Quantisation cost: −6.1 points HumanEval, −5.5 HumanEval+ against merged bf16.** Not significant at
  n=164 (p = 0.12 and 0.18), but the direction is consistent with the ~6-point loss seen for 4-bit NF4 and
  should be treated as real. Against the *base* bf16 the GGUF is −1.2 HumanEval and +1.8 HumanEval+, i.e.
  level with the original model, in the target format.
- **Merged bf16 is the best row (70.1 / 66.5)**, but its lead over the base is also inside the noise
  (p = 0.26 / 0.08). The earlier NF4 + runtime adapter row (65.9 / 61.6) scored lower than the merged
  model, so merging into bf16 is not equivalent to the NF4 + adapter model that was trained and
  validated. We do not claim the fine-tune improved correctness. The gap is about the size of the 4-bit
  penalty already measured on the base model: NF4 → bf16 is +4.2 / +4.9 points (HumanEval / HumanEval+)
  for the fine-tune (65.9 → 70.1, 61.6 → 66.5) and +6.1 / +4.8 for the base (59.1 → 65.2, 54.3 → 59.1),
  so it is consistent with NF4 quantisation cost rather than a real capability difference. This is
  arithmetic on existing runs, not a controlled test; each gap is 7–10 tasks, within the noise at n=164.
- **Format survives quantisation** (98.8% vs 100%), and the mean length is unchanged (167 tokens).
- Batch-size sensitivity: the merged bf16 run matched single-sequence decoding on 10/10 spot checks (the
  GGUF run was not checked this way).
- Throughput (CPU, this PC, 12 threads): 19 tokens/s generation, 71 tokens/s prompt processing in the
  single-stream smoke test; the full 164-task run took 15 min with 4 parallel slots. Model load took 32 s
  from a cold file cache.

Reproduce: `python training/export/merge_adapter.py ...`, convert and quantise with llama.cpp
(`convert_hf_to_gguf.py --outtype f16`, then `llama-quantize ... Q4_K_M`), then
`python humaneval_eval.py gen --config gguf_q4km --gguf <file>`, `score --config gguf_q4km`, and
`python report_tables.py base_bf16 merged_bf16 gguf_q4km`.

## Examples

**Fine-tune clearly helps: HumanEval/49 (`modp`).** The base model writes an explanation first, adds no
return hint, appends `print` test calls and a long "Explanation" section, and its code is wrong (it reduces
`n` modulo `p` before the exponent loop, which is not valid). The fine-tuned model returns only the block,
fully typed and documented, and passes:

```python
def modp(n: int, p: int) -> int:
    """Return 2^n modulo p (be aware of numerics).

    Args:
        n: The exponent to raise 2 to.
        p: The modulus to apply.

    Returns:
        The result of (2^n) % p.
    """
    result = 1
    base = 2
    while n > 0:
        if n % 2 == 1:
            result = (result * base) % p
        base = (base ** 2) % p
        n //= 2
    return result
```

**Fine-tune made it worse: HumanEval/36 (`fizz_buzz`).** The base model opens with a plain-English plan
("iterate through all numbers less than `n` divisible by 11 or 13…") and writes a correct loop. The
fine-tuned model skips the plan, produces well-formatted code, and gets the logic wrong:
`for i in range(11, n, 11) or range(13, n, 13)` only ever iterates the multiples of 11, because `or`
returns the first range. It fails. HumanEval/17 (`parse_music`) is the same pattern: perfect format, but the
code iterates characters instead of space-separated tokens, so `'o|'` is miscounted as a whole note and
`'.|'` never matches.

Across all tasks the fine-tune gained 18 and lost 17 against the bf16 base, so these are not isolated:
about as many tasks flip each way. A plausible, **untested** explanation for the losses is that the base
model's pre-code explanation works as a short chain of thought, and training the model to emit the code
block immediately removes it.

## Contamination check

`training/eval/contamination_check.py` compares the final 4,535 training examples (instruction **and**
response code) with HumanEval, HumanEval+, MBPP (all splits) and MBPP+ (1,680 items), using four signals.

1. **Instruction vs problem text** (word 3-gram, max of Jaccard and containment): no example reaches 0.3
   (maximum 0.296; 16 examples are above 0.2). This matches the pre-generation dedupe.
2. **Identical code:** 0 training functions are identical to a benchmark reference function after
   normalising away docstrings, annotations and comments.
3. **Shared word 8-grams** (ignoring 8-grams that occur in more than 3 training examples): 917 training
   examples share at least one with some benchmark item, touching 409 items. Reading the strongest HumanEval
   matches shows nearly all are generic code idioms in different tasks (e.g. a `find_islands` grid DFS vs
   `minPath`; `selection_sort` vs `triples_sum_to_zero`).
4. **Function-name collisions:** 147, almost all generic names (`is_prime` 16, `is_palindrome` 9,
   `__init__` 9, `factorial` 8, `fibonacci`, `merge_sort`, `binary_search`, …).

**Result: no copied benchmark problems or solutions, but some topical overlap on classic problems.**
- HumanEval/156 (int to Roman numeral) shares the standard Roman-numeral symbol table with one training
  example (a different spec: uppercase output, raises on non-positive input).
- HumanEval/71 (`triangle_area`) shares Heron's-formula code with training examples that implement the
  plain formula (the benchmark adds a validity check and rounding).
- HumanEval/55 (`fib`) is the same textbook task as a training example.
- **MBPP train/961** (Roman numeral to integer) has at least two clearly paraphrased training examples (five training examples overlap it). The
  instruction wording differs, so the lexical dedupe missed it. This matters if MBPP is evaluated later.

Excluding HumanEval 55, 71 and 156 changes pass@1 by at most 0.7 points (fine-tune 65.2%, bf16 base 64.6%,
NF4 base 59.0%), so the conclusions above do not depend on them. The check is lexical and structural; it
cannot find a paraphrased problem with different code.

## What this does and doesn't show

- **Shows:** the format was learned. 100% compliance on 164 unseen prompts, including the ones with
  helper functions and `typing` imports, and the model stops cleanly. This is a large, unambiguous change.
- **Shows:** no measurable loss of coding ability on these benchmarks relative to the base model at the same
  precision. Wins and losses are balanced.
- **Doesn't show:** that correctness is *improved*. The +0.7 / +2.5 point differences against the bf16 base
  are well inside the noise (±7 points at n=164, and McNemar p = 0.6–1.0). Greedy decoding with batch size 8
  also matched single-sequence decoding on only 4–8 of 10 spot-checked tasks (8/10 for the fine-tune, 6/10 for the bf16 base, 4/10 for the NF4 base), so
  small numeric differences already change individual answers.
- **The +6.8 points over the NF4 base is mostly quantisation, not fine-tuning.** The 4-bit base loses about
  6 points against bf16. The adapter was trained on top of the 4-bit weights, so it can plausibly compensate for that damage
  (not tested directly); the fair "did we regress" comparison is against bf16, where the change is zero. The model was
  then merged and quantised for serving, and re-measured: see "Exported model" above.
- **Expected:** this was a format-adaptation fine-tune on ~4.4k self-generated, assert-filtered examples, not
  a capability fine-tune. Unchanged correctness is the expected outcome; a large gain would have been
  suspicious.
- **Limits:** one benchmark family, 164 tasks, one greedy sample per task, no MBPP run, and the format
  checks are the project's own (single block, docstrings, hints, clean stop), not an independent standard.
  The model is evaluated on prompts phrased differently from its training instructions
  ("Complete the following function" with a docstring and signature), which is the harder case.

## Failure analysis: where the shipped model fails

The aggregate (64.0% HumanEval, 61.0% HumanEval+) hides what the failures are. Every task the shipped Q4_K_M GGUF
fails was re-run from its saved answer to find the first failing test case: the input, what the code returned and
what was expected (`training/eval/failure_analysis.py`; no new generation). All recorded failures reproduce: 59 on
HumanEval (52 wrong answers, 7 crashes) and 64 on HumanEval+, 65 distinct tasks (6 fail only HumanEval+'s extra cases).
All 65 answers are format-clean and stopped on their own: these are correctness failures, not format failures.

Each task got one primary category, assigned by reading the case (several are borderline). "Base also fails" compares
with the base model in bf16 on the same task; "failing input is in the prompt" means the first failing call is written
literally in the task's own docstring examples (a lower bound: prompts that state examples differently are not counted).

| Category | Failures | Base also fails | New vs base | Failing input is in the prompt |
|---|---|---|---|---|
| Dropped an explicit rule from the spec | 22 | 18 | 4 | 9 |
| Solved a familiar neighbouring problem instead | 8 | 7 | 1 | 6 |
| Wrong formula or algorithm | 14 | 6 | 8 | 7 |
| Off-by-one or boundary | 6 | 3 | 3 | 4 |
| Edge input (all HumanEval+ only) | 5 | 5 | 0 | 0 |
| Runtime error (2 are missing imports) | 7 | 6 | 1 | 3 |
| Typo-level slip | 3 | 1 | 2 | 1 |
| **Total** | **65** | **46** | **19** | **30** |

Fine-tuning fixed 21 tasks the base model fails and broke 19 it passes.

### Representative examples

- **Dropped a rule.** HumanEval/120 `maximum` returns `sorted(arr, reverse=True)[:k]`; the prompt's Example 1 needs
  ascending order (`[-3, -4, 5], 3` gives `[5, -3, -4]`, expected `[-4, -3, 5]`). HumanEval/108 `count_nums` ignores
  the stated rule that "-123 has signed digits -1, 2, and 3" (`[-1, -2, 0]` gives 2, expected 0).
- **Neighbouring problem.** HumanEval/26 `remove_duplicates` writes ordinary de-duplication; the spec asks to remove
  every element that occurs more than once (its own example: `[1, 2, 3, 2, 4]` is `[1, 3, 4]`). HumanEval/139
  `special_factorial` writes a plain factorial (4 gives 24; the prompt's example says 288).
- **Wrong formula or algorithm.** HumanEval/138 `is_equal_to_sum_even` tests `(n - 8) % 4 == 0`, so 10 gives False
  (any even n >= 8 is a sum of four positive evens). HumanEval/38 `decode_cyclic` reverses each group of three instead
  of undoing the rotation.
- **Off-by-one.** HumanEval/127 `intersection` takes the length as `end - start + 1`: (-1, 1) and (0, 4) overlap in
  (0, 1), length 1, not prime, so "NO"; the code computes 2 and answers "YES". HumanEval/123 `get_odd_collatz` stops
  the sequence before 1, so 1 is missing.
- **Edge input.** HumanEval/22 `filter_integers` keeps `True` and `False` (`bool` is a subclass of `int`).
  HumanEval/44 `change_base(0, 3)` returns `''` instead of `'0'`.
- **Runtime error.** HumanEval/136 annotates its return as `Tuple[Optional[int], Optional[int]]` but imports only
  `List, Tuple`, so it fails with a NameError when the function is defined. This one comes from the fine-tune's
  type-hint habit; the base model passes the task. HumanEval/77 `iscube(-1)`: the cube root of a negative number is
  complex in Python, and `round()` rejects it.
- **Typo-level slip.** HumanEval/79 has a stray `.` in the f-string (`f"db{...}.db"`). HumanEval/91 calls
  `S.split('.?!')`, which splits on that three-character string, not on any of the three characters.

### What this says about a second fine-tune

- **Spec reading dominates, and it is inherited.** 30 of 65 failures drop a rule or solve a neighbouring problem, and
  25 of those 30 fail for the base model too. The format fine-tune neither caused nor fixed them; a second fine-tune
  aimed at correctness would need data that rewards following every stated rule, not more format examples.
- **About half the failures contradict the prompt's own examples.** 30 of 65 fail on an input written in their own
  docstring. Two ways to use that: filter training data by running the prompt's examples as well as the generated
  tests, or an inference-time self-check that runs them and retries. Caution: HumanEval's tests include those same
  examples, so a self-check would inflate pass@1 and the result would not be comparable with the numbers above.
- **A cheap fix with no training:** the format checks now flag any name used in a type hint that is never imported
  (`format_checks.py`, reason `unimported_hint_name`), in both the training-data filter and eval scoring. Over the
  five saved eval runs (820 answers) it flags exactly one answer per run where it applies: HumanEval/136, in the
  shipped GGUF and in the checkpoint it came from; no false positives. Both runs were re-scored with it: the shipped
  model's format-clean rate is now 162/164 (98.8%, was 99.4%), checkpoint-250's 163/164 (99.4%, was 100%). The SFT data had 6 such examples out of 4,535 (`Generator`, `Callable`, `Tuple`,
  `Foo`), all in quoted annotations, which do not fail at runtime; HumanEval/136's was unquoted, which does.
- **Tuple immutability does not show up here.** No HumanEval failure is an assignment into a tuple. The playground's
  merge_intervals recording fails exactly that way (`merged[-1][1] = ...` on a tuple), but HumanEval cannot measure it;
  scoping training on it would need its own probe set first.
- **Limits.** One label per task, assigned by hand. 164 tasks give about ±7 points of noise, and per-category counts
  of 5 to 8 are too small to scope a training run on their own.

## Reproduction

```bash
cd training/eval
python humaneval_eval.py gen   --config ckpt250 --check-bs1 10   # also: base_nf4, base_bf16
python humaneval_eval.py score --config ckpt250
python humaneval_eval.py table
python contamination_check.py
python failure_analysis.py diagnose && python failure_analysis.py table   # saved outputs only
```

Outputs go to `~/work/eval/` (outside the repo). Execution uses the data pipeline's sandbox
(`exec_check.py`: temp dir, empty environment, rlimits, timeout; 10 s for HumanEval, 40 s for HumanEval+).
