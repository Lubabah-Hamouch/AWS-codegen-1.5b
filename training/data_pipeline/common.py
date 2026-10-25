"""Shared paths and constants for the data pipeline."""

import os
from pathlib import Path

# Heavy artifacts (datasets, generations) live outside the repo, on the Linux filesystem.
WORK = Path(os.environ.get("PLAYGROUND_WORK", Path.home() / "work"))
DATA_DIR = WORK / "data"

SOURCE_DATASET = "bigcode/self-oss-instruct-sc2-exec-filter-50k"
BASE_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
SEED = 42


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
