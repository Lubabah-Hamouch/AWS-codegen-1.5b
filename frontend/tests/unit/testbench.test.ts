import { afterEach, describe, expect, it, vi } from "vitest";
import { EXAMPLES } from "@/data/facts";
import { SUITE_COUNT, suiteFor } from "@/data/checks";
import { RUN_LIMIT_MS, runBench, summarize, type BenchResult } from "@/lib/testbench";

// A stand-in for the Pyodide worker: boots, then either answers with `reply` or never answers (a runaway loop).
class FakeWorker {
  static last: FakeWorker;
  static ran: FakeWorker | null = null; // the worker that received the code (runBench reuses a pre-warmed spare)
  static reply: unknown = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  terminated = false;
  private ls: ((e: { data: unknown }) => void)[] = [];
  constructor() {
    FakeWorker.last = this;
    setTimeout(() => this.ls.forEach((l) => l({ data: { type: "ready" } })), 10);
  }
  addEventListener(type: string, l: (e: { data: unknown }) => void) {
    if (type === "message") this.ls.push(l);
  }
  postMessage() {
    FakeWorker.ran = this;
    if (FakeWorker.reply) setTimeout(() => this.onmessage?.({ data: FakeWorker.reply }), 20);
  }
  terminate() {
    this.terminated = true;
  }
}

const result = (over: Partial<BenchResult>): BenchResult =>
  ({ python: "3.14", stage: "done", defined: ["f"], target: "f", stdout: "", error: null, checks: [], ...over });

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("runBench", () => {
  it("kills a run that is still going at the limit", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("Worker", FakeWorker);
    FakeWorker.reply = null;
    const p = runBench("while True: pass", null);
    await vi.advanceTimersByTimeAsync(RUN_LIMIT_MS + 50);
    expect(await p).toMatchObject({ kind: "timeout" });
    expect(FakeWorker.ran?.terminated).toBe(true);
  });
  it("returns the worker's result and always terminates the worker", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("Worker", FakeWorker);
    FakeWorker.reply = { type: "result", result: result({}) };
    const p = runBench("def f(): pass", null);
    await vi.advanceTimersByTimeAsync(100);
    expect((await p).kind).toBe("result");
    expect(FakeWorker.ran?.terminated).toBe(true);
    expect(FakeWorker.last).not.toBe(FakeWorker.ran); // a fresh spare was started for the next run
  });
});

describe("summarize: pass/fail only with a suite", () => {
  it("never claims pass/fail without a suite", () => {
    const s = summarize({ kind: "result", ms: 1, result: result({ defined: ["fibonacci"] }) }, false);
    expect(s.headline).toBe("Runs and defines fibonacci");
    expect(s.headline + s.detail).not.toMatch(/pass|✓|✗/);
  });
  it("counts checks with a suite, honestly", () => {
    const rows = [{ ok: true }, { ok: false }, { ok: true }].map((r, i) => ({ call: `f(${i})`, expect: "1", got: "1", error: null, ...r }));
    expect(summarize({ kind: "result", ms: 1, result: result({ checks: rows }) }, true).headline).toBe("✗ 2/3 checks pass");
    expect(summarize({ kind: "result", ms: 1, result: result({ checks: rows.map((r) => ({ ...r, ok: true })) }) }, true).headline).toBe("✓ 3/3 checks pass");
  });
  it("reports parse errors with the line, and timeouts", () => {
    const parse = result({ stage: "parse", error: { type: "SyntaxError", msg: "invalid syntax", line: 4 } });
    expect(summarize({ kind: "result", ms: 1, result: parse }, true)).toMatchObject({ headline: "Does not parse", detail: "SyntaxError on line 4: invalid syntax" });
    expect(summarize({ kind: "timeout", ms: 5000 }, true).headline).toBe("Stopped after 5 s");
  });
});

describe("suites", () => {
  it("exist for exactly the five example prompts, unedited", () => {
    expect(SUITE_COUNT).toBe(EXAMPLES.length);
    for (const p of EXAMPLES) expect(suiteFor(p)?.checks.length).toBeGreaterThanOrEqual(4);
    expect(suiteFor(EXAMPLES[0] + " Use recursion.")).toBeNull();
    expect(suiteFor("Write a function that adds two numbers.")).toBeNull();
  });
});
