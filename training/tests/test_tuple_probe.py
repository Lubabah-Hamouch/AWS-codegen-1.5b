import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "data_pipeline"))

from probes.tuple_tasks import MUTANTS, TASKS  # noqa: E402
from tuple_probe import run  # noqa: E402

BY_ID = {t["id"]: t for t in TASKS}


def test_forty_tasks_with_unique_ids():
    assert len(TASKS) == 40 and len(BY_ID) == 40


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_reference_solution_is_correct_and_leaves_input_alone(task):
    r = run(task["reference"], task)
    assert (r["outcome"], r["mutated_input"]) == ("correct", False), r


@pytest.mark.parametrize("tid,want,code", MUTANTS, ids=[f"{m[0]}-{m[1]}" for m in MUTANTS])
def test_scorer_labels_each_known_mistake(tid, want, code):
    r = run(code, BY_ID[tid])
    got = "mutated_input" if want == "mutated_input" and r["mutated_input"] else r["outcome"]
    assert got == want, r
