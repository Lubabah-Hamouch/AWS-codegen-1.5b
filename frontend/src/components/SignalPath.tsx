import type { ReactNode } from "react";
import { BUDGET, EXAMPLES, HOST, MODEL, PERF } from "@/data/facts";
import { MAX_PROMPT_CHARS } from "@/lib/api";
import type { ReplayIndexEntry } from "@/lib/replay";
import { RunState, active } from "@/lib/runMachine";
import type { SiteStatus } from "@/lib/status";

export type Mode = "live" | "replay";

type Props = {
  run: RunState;
  mode: Mode;
  liveAllowed: boolean;
  onMode: (m: Mode) => void;
  prompt: string;
  onPrompt: (p: string) => void;
  replays: ReplayIndexEntry[];
  replayId: string | null;
  onReplay: (id: string) => void;
  onRun: () => void;
  onStop: () => void;
  status: SiteStatus;
  remaining: number | null;
  lastCode: string | null;
};

function Conn({ label, sub, live, double }: { label: string; sub: ReactNode; live: boolean; double?: boolean }) {
  return (
    <div className={`conn${live ? " live" : ""}`} aria-hidden="true">
      <span className="cu">{label}</span>
      <svg viewBox="0 0 72 16">
        {double ? (
          <>
            <line className="wire" x1="0" y1="5" x2="72" y2="5" />
            <line className="wire2" x1="0" y1="11" x2="72" y2="11" />
          </>
        ) : (
          <>
            <line className="wire" x1="0" y1="8" x2="72" y2="8" />
            <circle className="via" cx="36" cy="8" r="3.5" />
          </>
        )}
      </svg>
      <span>{sub}</span>
    </div>
  );
}

export function SignalPath(p: Props) {
  const { run } = p;
  const running = active(run);
  const streaming = run.phase === "streaming";
  const killLabel = p.status.live === false ? "engaged" : p.status.live === true ? "open" : "unknown";
  const breaker = p.status.note === "circuit breaker" ? "tripped" : "armed";
  const slot = running && run.source === "live" ? "held 1 / 2" : p.lastCode === "busy" ? "full 2 / 2" : `free · cap ${BUDGET.concurrency}`;
  const quota = p.remaining !== null ? `${p.remaining} / ${BUDGET.anonPerIp} left` : `${BUDGET.anonPerIp} / day`;
  const tooLong = p.prompt.length > MAX_PROMPT_CHARS;

  return (
    <div className="path" id="controls" tabIndex={-1}>
      <section className="blk u1" aria-labelledby="u1">
        <h2 id="u1" className="silk"><span>U1 · Spec in</span><span className="au">J1</span></h2>
        <div className="srcsw silk" role="group" aria-label="Source">
          <button type="button" aria-pressed={p.mode === "live"} onClick={() => p.onMode("live")} disabled={!p.liveAllowed || running}
            title={p.liveAllowed ? "Generate live on Lambda" : "Live generation is paused"}>Live</button>
          <button type="button" aria-pressed={p.mode === "replay"} onClick={() => p.onMode("replay")} disabled={running}>Replay</button>
        </div>
        {p.mode === "live" ? (
          <>
            <label htmlFor="spec" className="dim" style={{ fontSize: 12 }}>
              describe one Python function · {p.prompt.length} / {MAX_PROMPT_CHARS} ch
              {tooLong && <span className="tp"> · too long</span>}
            </label>
            <textarea id="spec" className="spec" rows={3} value={p.prompt} maxLength={MAX_PROMPT_CHARS + 200}
              onChange={(e) => p.onPrompt(e.target.value)} readOnly={running}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!running) p.onRun(); } }} />
            <div className="chips" aria-label="Example prompts">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => p.onPrompt(ex)} disabled={running} title={ex}>
                  {ex.replace(/^Write a (Python )?function that /, "").slice(0, 34)}…
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <span className="dim" style={{ fontSize: 12 }}>recorded runs · real output, real timing</span>
            <div className="chips" role="group" aria-label="Recorded runs">
              {p.replays.map((r) => (
                <button key={r.id} type="button" aria-pressed={r.id === p.replayId} onClick={() => p.onReplay(r.id)} disabled={running}>{r.title}</button>
              ))}
              {!p.replays.length && <span className="dim">loading…</span>}
            </div>
            <textarea className="spec" rows={2} readOnly aria-label="Recorded prompt"
              value={p.replays.find((r) => r.id === p.replayId)?.prompt ?? ""} />
          </>
        )}
        <div className="runrow">
          {running ? (
            <button type="button" className="btn-run btn-stop silk" onClick={p.onStop}>Stop ■</button>
          ) : (
            <button type="button" className="btn-run silk" onClick={p.onRun}
              disabled={p.mode === "live" ? !p.prompt.trim() || tooLong : !p.replayId}>
              {p.mode === "live" ? "Run ▸" : "Replay ▸"}
            </button>
          )}
          <span className="dim" style={{ fontSize: 11 }}>
            {p.mode === "live" ? <><kbd>Ctrl</kbd>+<kbd>Enter</kbd> · {quota}</> : "plays in your browser · no backend call"}
          </span>
        </div>
      </section>

      <Conn label={p.mode === "live" ? "POST" : "file"} sub={<span className="dim">{p.mode === "live" ? "/generate" : "replay"}</span>} live={running} />

      <section className="blk u2" aria-labelledby="u2">
        <h2 id="u2" className="silk"><span>U2 · Guard</span>{p.mode === "replay" && <span className="dim tag">bypassed</span>}</h2>
        <div className="kv"><span>KILL</span><span className={killLabel === "engaged" ? "tp" : ""}>{killLabel}</span></div>
        <div className="kv"><span>SLOT</span><span className="au">{slot}</span></div>
        <div className="kv"><span>QUOTA·IP</span><span className="au">{quota}</span></div>
        <div className="kv"><span>GLOBAL</span><span>{BUDGET.globalDaily} / day</span></div>
        <div className="kv"><span>BREAKER</span><span className={breaker === "tripped" ? "tp" : ""}>{breaker} · &gt;{BUDGET.breakerPer5Min}/5m</span></div>
        <div className="kv"><span>LAST</span><span className={p.lastCode && p.lastCode !== "ok" ? "tp" : ""}>{p.lastCode ?? "—"}</span></div>
      </section>

      <Conn label="admit" sub={<span className="tp">TP1</span>} live={running} />

      <section className={`blk u3${running ? " active" : ""}`} aria-labelledby="u3">
        <h2 id="u3" className="silk"><span>U3 · Model</span><span className={running ? "au" : "dim"}>{running ? (streaming ? "decode" : "prefill") : "idle"}</span></h2>
        <div className="kv"><span>WEIGHTS</span><span>{MODEL.quant} · {MODEL.sizeMb} MB</span></div>
        <div className="kv"><span>THREADS</span><span>{HOST.threads} · greedy · seed 42</span></div>
        <div className="kv"><span>RSS</span><span>{HOST.rssPeakMb} / {HOST.memoryMb} MB <span className="dim tag">bench</span></span></div>
        <div className="kv"><span>BILLED</span><span>{PERF.billedS} s · {PERF.gbS} GB·s <span className="dim tag">bench</span></span></div>
        <div className="kv"><span>COLD</span><span>{HOST.coldStart}</span></div>
      </section>

      <Conn label={`SSE ×${run.tokenTimes.length}`} sub={<span className="tp">TP2 · TP3</span>} live={streaming} double />

      <section className="blk u4" aria-labelledby="u4">
        <h2 id="u4" className="silk"><span>U4 · Stream</span>{run.source === "replay" && run.phase !== "idle" && <span className="sig2 tag">replay</span>}</h2>
        <div className="kv"><span>events</span><span>{run.tokenTimes.length}</span></div>
        <div className="kv"><span>done</span><span>{run.done?.finish_reason ?? (run.phase === "error" ? "error" : "—")}</span></div>
        <div className="kv"><span>wall</span><span>{run.phase === "idle" ? "—" : `${(run.elapsedMs / 1000).toFixed(1)} s`}</span></div>
        <div className="kv"><span className="tp">TP4</span><span>{run.done ? (run.done.finish_reason === "stop" ? "clean EOS" : run.done.finish_reason) : "—"}</span></div>
      </section>
    </div>
  );
}
