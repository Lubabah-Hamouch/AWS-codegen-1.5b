import { PERF } from "@/data/facts";
import { RunState, active, firstTokenMs, liveRate, rateSeries } from "@/lib/runMachine";

const PHASE_LABEL: Record<RunState["phase"], string> = {
  idle: "IDLE", connecting: "ADMIT", streaming: "DECODE", done: "EOS", error: "FAULT", stopped: "HALT",
};

export function Readouts({ run }: { run: RunState }) {
  const ft = firstTokenMs(run);
  const rate = run.done?.tok_s ?? liveRate(run);
  const tokens = run.done?.tokens ?? (run.tokenTimes.length || null);
  const waitingLong = run.phase === "connecting" && run.elapsedMs > 2500;
  const finish = run.phase === "done" ? (run.done?.finish_reason === "stop" ? "EOS" : (run.done?.finish_reason ?? "?").toUpperCase()) : PHASE_LABEL[run.phase];

  return (
    <div className="readouts" role="group" aria-label="Test point readouts">
      <div className="ro">
        <span className="lab silk"><span className="tp">● TP1</span><span className="dim">first token</span></span>
        <span className="val au">{ft !== null ? (ft / 1000).toFixed(2) : run.phase === "connecting" ? (run.elapsedMs / 1000).toFixed(1) : "—"}<small> s</small></span>
        <span className="sub">{waitingLong ? "cold start likely: 4–9 s" : ft !== null ? `client-side${run.done?.ttft_s != null ? ` · server ${run.done.ttft_s.toFixed(2)} s` : ""}` : "request → first token"}</span>
      </div>
      <div className="ro">
        <span className="lab silk"><span className="tp">● TP2</span><span className="dim">decode rate</span></span>
        <span className="val au">{rate ? rate.toFixed(1) : "—"}<small> tok/s</small></span>
        <span className="sub">{run.done?.tok_s ? "server-measured" : rate ? "live estimate" : `median ${PERF.tokS} · spread ${PERF.tokSSpread[0]}–${PERF.tokSSpread[1]}`}</span>
      </div>
      <div className="ro">
        <span className="lab silk"><span className="tp">● TP3</span><span className="dim">tokens out</span></span>
        <span className="val">{tokens ?? "—"}<small> / 512</small></span>
        <span className="sub">{run.done?.prompt_tokens ? `+${run.done.prompt_tokens} prompt tokens` : `${(run.elapsedMs / 1000).toFixed(1)} s wall`}</span>
      </div>
      <div className={`ro${active(run) ? " hot" : ""}`}>
        <span className="lab silk"><span className="tp">● TP4</span><span className="dim">{run.phase === "done" ? "finish" : "phase"}</span></span>
        <span className={`val ${run.phase === "error" ? "tp" : "cu"}`} aria-live="polite">{finish}</span>
        <span className="sub">{run.phase === "done" ? `${run.done?.finish_reason} · ${(run.elapsedMs / 1000).toFixed(1)} s` : run.phase === "idle" ? "ready" : run.source === "replay" ? "recorded run" : "live"}</span>
      </div>
      <div className="ro trace">
        <span className="lab silk"><span className="tp">● TP2</span><span className="dim">rate trace · 0–25 tok/s · dashed = median {PERF.tokS}</span></span>
        <RateTrace times={run.tokenTimes} />
        {run.phase === "idle" && <span className="sub">speed over time, plotted as tokens arrive</span>}
      </div>
    </div>
  );
}

function RateTrace({ times }: { times: number[] }) {
  const series = rateSeries(times);
  const W = 300, H = 64, top = 25; // fixed scale 0-25 tok/s so runs compare
  const pts = series.map((v, i) => `${series.length > 1 ? (i / (series.length - 1)) * W : 0},${H - 4 - (Math.min(v, top) / top) * (H - 10)}`);
  const y = (v: number) => H - 4 - (v / top) * (H - 10);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label={series.length ? `Decode rate over ${times.length} tokens, last ${series[series.length - 1].toFixed(1)} tok/s` : "No run yet"}>
      {[5, 10, 15, 20].map((g) => (
        <line key={g} x1="0" x2={W} y1={y(g)} y2={y(g)} stroke="var(--gutline)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      <line x1="0" x2={W} y1={y(PERF.tokS)} y2={y(PERF.tokS)} stroke="var(--line)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      {pts.length > 1 && <polyline points={pts.join(" ")} fill="none" stroke="var(--au)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />}
    </svg>
  );
}
