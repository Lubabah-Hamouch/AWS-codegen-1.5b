// In-browser test bench: runs the generated code in a throwaway Web Worker (public/testbench.worker.mjs, Pyodide).
// Nothing loads until the first run. Each run gets a fresh worker that is terminated afterwards; a spare is booted
// in the background after a run so the next one does not wait for Python to start again.

import type { Suite } from "@/data/checks";

export const RUN_LIMIT_MS = 5000; // generated code + checks
export const BOOT_LIMIT_MS = 90_000; // first use downloads ~6 MB

export type CheckRow = { call: string; expect: string; ok: boolean; got: string | null; error: PyError | null };
export type PyError = { type: string; msg: string; line: number | null };
export type BenchResult = {
  python: string;
  stage: "parse" | "exec" | "done";
  defined: string[];
  target: string | null;
  stdout: string;
  error: PyError | null;
  checks: CheckRow[];
};
export type Outcome =
  | { kind: "result"; result: BenchResult; ms: number }
  | { kind: "timeout"; ms: number }
  | { kind: "boot_failed"; message: string };

type Booted = { worker: Worker; ready: Promise<boolean> };

function boot(): Booted {
  const worker = new Worker("/testbench.worker.mjs", { type: "module" });
  const ready = new Promise<boolean>((resolve) => {
    const t = setTimeout(() => resolve(false), BOOT_LIMIT_MS);
    worker.addEventListener("message", (e) => {
      if (e.data?.type === "ready" || e.data?.type === "boot_failed") {
        clearTimeout(t);
        resolve(e.data.type === "ready");
      }
    }, { once: true });
    worker.addEventListener("error", () => { clearTimeout(t); resolve(false); }, { once: true });
  });
  return { worker, ready };
}

let spare: Booted | null = null;

/** Starts Python loading ahead of time (e.g. when the listing finishes), without running anything. */
export function prewarm() {
  spare ??= boot();
}

export async function runBench(code: string, suite: Suite | null, onBooted?: () => void): Promise<Outcome> {
  const b = spare ?? boot();
  spare = null;
  if (!(await b.ready)) {
    b.worker.terminate();
    return { kind: "boot_failed", message: "Python (WebAssembly) failed to start in this browser" };
  }
  onBooted?.();
  const t0 = performance.now();
  const outcome = await new Promise<Outcome>((resolve) => {
    const t = setTimeout(() => resolve({ kind: "timeout", ms: RUN_LIMIT_MS }), RUN_LIMIT_MS);
    b.worker.onmessage = (e) => {
      clearTimeout(t);
      if (e.data?.type === "result") resolve({ kind: "result", result: e.data.result, ms: performance.now() - t0 });
      else resolve({ kind: "boot_failed", message: e.data?.message ?? "worker error" });
    };
    b.worker.postMessage({ code, suite });
  });
  b.worker.terminate(); // always: a timed-out loop is killed here, and no state survives into the next run
  prewarm();
  return outcome;
}

export type Summary = { tone: "ok" | "bad" | "neutral"; headline: string; detail: string };

/** One honest line about an outcome. Pass/fail only exists when there is a suite; otherwise behaviour only. */
export function summarize(o: Outcome, hasSuite: boolean): Summary {
  if (o.kind === "boot_failed") return { tone: "neutral", headline: "Could not start Python", detail: o.message };
  if (o.kind === "timeout")
    return { tone: "bad", headline: `Stopped after ${RUN_LIMIT_MS / 1000} s`, detail: "Still running at the limit (likely an endless loop); the worker was terminated." };
  const r = o.result;
  const at = (e: PyError) => (e.line ? ` on line ${e.line}` : "");
  if (r.error && r.stage === "parse") return { tone: "bad", headline: "Does not parse", detail: `SyntaxError${at(r.error)}: ${r.error.msg}` };
  if (r.error) return { tone: "bad", headline: "Raises while loading", detail: `${r.error.type}${at(r.error)}: ${r.error.msg}` };
  const defs = r.defined.length ? `defines ${r.defined.join(", ")}` : "defines no function or class";
  if (!hasSuite) return { tone: "neutral", headline: `Runs and ${defs}`, detail: "No checks: this is not one of the example prompts." };
  if (!r.checks.length) return { tone: "bad", headline: `Runs, but ${defs}`, detail: "There is no function to check." };
  const passed = r.checks.filter((c) => c.ok).length;
  const all = passed === r.checks.length;
  return { tone: all ? "ok" : "bad", headline: `${all ? "✓" : "✗"} ${passed}/${r.checks.length} checks pass`, detail: `Checked ${r.target}() with this example's hand-written checks.` };
}
