import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { suiteFor } from "@/data/checks";
import { extractCode } from "@/lib/python";
import type { RunState } from "@/lib/runMachine";
import { Outcome, RUN_LIMIT_MS, runBench, summarize } from "@/lib/testbench";

type Phase = "idle" | "booting" | "running" | "done";

export function TestBench({ run }: { run: RunState }) {
  const code = useMemo(() => extractCode(run.text), [run.text]);
  // checks only for a complete answer to an unedited example prompt
  const suite = run.phase === "done" ? suiteFor(run.prompt) : null;
  const ready = (run.phase === "done" || run.phase === "stopped") && !!code;
  const [phase, setPhase] = useState<Phase>("idle");
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => { setPhase("idle"); setOutcome(null); }, [run.text, run.prompt]);

  const go = async () => {
    setOutcome(null);
    setPhase("booting");
    const o = await runBench(code, suite, () => setPhase("running"));
    setOutcome(o);
    setPhase("done");
  };

  const s = outcome ? summarize(outcome, !!suite) : null;
  const rows = outcome?.kind === "result" ? outcome.result.checks : [];
  const busy = phase === "booting" || phase === "running";

  return (
    <section className="blk bench" aria-labelledby="u6">
      <h2 id="u6" className="silk">
        <span>U6 · Test bench</span>
        <span className="dim">{outcome?.kind === "result" ? `python ${outcome.result.python} · wasm` : "in your browser"}</span>
      </h2>
      <div className="runrow">
        <button type="button" className="btn-run silk" onClick={go} disabled={!ready || busy}>
          {suite ? "Run checks ▸" : "Run code ▸"}
        </button>
        <span className="dim" style={{ fontSize: 12 }} aria-live="polite">
          {busy ? (phase === "booting" ? "starting Python… (first use downloads ~6 MB)" : "running…")
            : !ready ? "available when a listing has finished"
            : suite ? `${suite.checks.length} hand-written checks for this example prompt`
            : run.phase === "stopped" ? "partial output: runs it, no checks"
            : "custom prompt: reports what the code does, no pass/fail"}
        </span>
      </div>

      {s && (
        <div className={`bench-sum ${s.tone}`} role="status">
          <strong>{s.headline}</strong> <span className="dim">{s.detail}</span>
        </div>
      )}

      {rows.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl bench-tbl">
            <caption className="sr-only">Check results</caption>
            <thead>
              <tr><th scope="col"></th><th scope="col">call</th><th scope="col">expected</th><th scope="col">got</th></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.call}>
                  <td className={c.ok ? "sig2" : "tp"} aria-label={c.ok ? "pass" : "fail"}>{c.ok ? "✓" : "✗"}</td>
                  <th scope="row" style={{ fontWeight: 400 }}><code>{c.call}</code></th>
                  <td><code>{c.expect}</code></td>
                  <td className={c.ok ? "" : "tp"}><code>{c.error ? `${c.error.type}: ${c.error.msg}${c.error.line ? ` (listing line ${c.error.line})` : ""}` : c.got}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {outcome?.kind === "result" && outcome.result.stdout && (
        <pre className="pinout" aria-label="Printed output">{outcome.result.stdout}</pre>
      )}

      <p className="note" style={{ borderLeftColor: "var(--sig2)" }}>
        {suite
          ? <>Hand-written checks for this one example prompt{suite.convention ? `; assumes ${suite.convention}` : ""}. They test this spec, not the model in general; <Link href="/notes/#eval">HumanEval</Link> is the general measure.</>
          : <>Checks exist only for the five example prompts, unedited. For anything else this reports whether the code runs and what it defines, never pass/fail.</>}
        {" "}Runs in a throwaway Web Worker (Pyodide), {RUN_LIMIT_MS / 1000} s limit, network limited to this site and its API.
      </p>
    </section>
  );
}
