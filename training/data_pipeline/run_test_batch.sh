#!/usr/bin/env bash
# Steps 1-5 on a small batch. Usage: run_test_batch.sh [num_prompts] [samples_per_prompt]
set -euo pipefail
cd "$(dirname "$0")"
export HF_HOME=${HF_HOME:-$HOME/work/hf} PYTHONDONTWRITEBYTECODE=1 HF_HUB_DISABLE_PROGRESS_BARS=1
PY=${PY:-$HOME/venvs/playground/bin/python}
OUT=$HOME/work/data/test_batch.jsonl
$PY prepare_prompts.py | grep -E '"(kept|removed|threshold)"'
rm -f "$OUT"
$PY generate.py --out "$OUT" --limit "${1:-30}" -n "${2:-4}"
$PY filter_generations.py "$OUT"
