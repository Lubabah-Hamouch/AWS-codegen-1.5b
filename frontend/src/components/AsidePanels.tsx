import Link from "next/link";
import { BUDGET, EVAL, PERF } from "@/data/facts";
import { PLAIN } from "@/data/key";
import type { RunRecord } from "@/lib/history";

export function EvalPanel() {
  return (
    <section className="blk" aria-labelledby="u5">
      <h2 id="u5" className="silk"><span>U5 · Eval · shipped GGUF</span><Link href="/notes/#eval" className="dim">→</Link></h2>
      <p className="blk-sub">{PLAIN.u5}</p>
      <div className="kv"><span>HumanEval pass@1</span><span className="au">{EVAL.humaneval.toFixed(1)}%</span></div>
      <div className="kv"><span>HumanEval+ pass@1</span><span>{EVAL.humanevalPlus.toFixed(1)}%</span></div>
      <div className="kv"><span>format clean</span><span>{EVAL.formatClean}%</span></div>
      <div className="kv"><span>base, same format</span><span>{EVAL.base.formatClean}%</span></div>
      <span className="dim" style={{ fontSize: 11 }}>164 tasks · greedy · as served (typing import fix; model output alone:
        {" "}{EVAL.model.humaneval.toFixed(1)} / {EVAL.model.humanevalPlus.toFixed(1)} / {EVAL.model.formatClean}%) · level with the base on correctness (±7 pt noise)</span>
    </section>
  );
}

export function BudgetPanel() {
  return (
    <section className="blk" aria-labelledby="r1">
      <h2 id="r1" className="silk"><span>R1 · Budget</span><Link href="/notes/#capacity" className="dim">→</Link></h2>
      <p className="blk-sub">{PLAIN.r1}</p>
      <div className="kv"><span>per visitor</span><span>{BUDGET.anonPerIp} live / day</span></div>
      <div className="kv"><span>global cap</span><span>{BUDGET.globalDaily} / day</span></div>
      <div className="kv"><span>per generation</span><span>{PERF.gbS} GB·s</span></div>
      <div className="kv"><span>free tier</span><span>~{BUDGET.genPerMonthWarm.toLocaleString("en-US")} / mo</span></div>
      <div className="kv"><span>worst case/mo</span><span>{(BUDGET.worstCaseGbS / 1000).toFixed(0)}k of 400k GB·s</span></div>
    </section>
  );
}

export function RunLog({ runs }: { runs: RunRecord[] }) {
  return (
    <section className="blk" aria-labelledby="log">
      <h2 id="log" className="silk"><span>Run log · this browser</span><span className="dim">{runs.length}</span></h2>
      {runs.length ? (
        <table className="runlog">
          <thead>
            <tr><th>utc</th><th>src</th><th>prompt</th><th>tok</th><th>tok/s</th><th>end</th></tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.at + r.prompt}>
                <td className="dim">{r.at.slice(11, 16)}</td>
                <td className={r.source === "live" ? "au" : "sig2"}>{r.source === "live" ? "L" : "R"}</td>
                <td className="p" title={r.prompt}>{r.prompt}</td>
                <td>{r.tokens ?? "—"}</td>
                <td>{r.tok_s?.toFixed(1) ?? "—"}</td>
                <td className={r.outcome === "stop" ? "" : "tp"}>{r.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <span className="dim" style={{ fontSize: 12 }}>No runs yet. L = live, R = replay.</span>
      )}
    </section>
  );
}
