import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { fixTypingImports } from "@/lib/typingFix";

// The same cases drive training/tests/test_typing_fix.py (expected values come from the Python fixer), so the
// browser's fix and the one the evals were scored with stay identical.
type Case = { name: string; code: string; added: string[]; fixed: string };
const CASES: Case[] = JSON.parse(readFileSync(new URL("../../../training/data_pipeline/typing_fix_cases.json", import.meta.url), "utf8")).cases;

describe("typing import fix (shared cases with the Python fixer)", () => {
  it.each(CASES.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const r = fixTypingImports(c.code);
    expect(r.added).toEqual(c.added);
    expect(r.code).toBe(c.fixed);
    if (c.added.length) expect(r.code.split("\n")[r.line! - 1]).toMatch(/^from typing import /);
    else expect(r.line).toBeNull();
  });

  it("ignores brackets, colons and typing names inside strings and comments", () => {
    const code = 'def f(a: int = ":(", b: str = "Tuple[") -> int:  # returns List\n    """Optional docs."""\n    return 0\n';
    expect(fixTypingImports(code).added).toEqual([]);
  });
});
