import ast
import json
import sys
from pathlib import Path

import pytest

DP = Path(__file__).resolve().parents[1] / "data_pipeline"
sys.path.insert(0, str(DP))

from format_checks import check_response, unimported_hint_names  # noqa: E402
from typing_fix import fix_response, fix_typing_imports  # noqa: E402

# The same cases drive frontend/tests/unit/typingFix.test.ts, so the two implementations stay in step.
CASES = json.loads((DP / "typing_fix_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_shared_case(case):
    assert fix_typing_imports(case["code"]) == (case["fixed"], case["added"])


@pytest.mark.parametrize("case", [c for c in CASES if c["added"]], ids=lambda c: c["name"])
def test_fixed_code_parses_and_only_import_lines_change(case):
    tree = ast.parse(case["fixed"])
    assert not (unimported_hint_names(tree) & set(case["added"]))
    before, after = case["code"].split("\n"), case["fixed"].split("\n")
    changed = [ln for ln in after if ln not in before] + [ln for ln in before if ln not in after]
    assert changed and all(ln.startswith("from typing import") for ln in changed)


def test_response_fix_makes_humaneval_136_format_clean():
    case = next(c for c in CASES if c["name"] == "humaneval_136_optional_missing")
    text = "```python\n" + case["code"] + "```"
    assert "unimported_hint_name" in check_response(text, True)
    fixed, added = fix_response(text)
    assert added == ["Optional"]
    assert "unimported_hint_name" not in check_response(fixed, True)
    assert fixed.startswith("```python\nfrom typing import List, Tuple, Optional\n")
