import Head from "next/head";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { BudgetPanel, EvalPanel, RunLog } from "@/components/AsidePanels";
import { Listing } from "@/components/Listing";
import { Intro } from "@/components/Intro";
import { Footer, Masthead } from "@/components/Masthead";
import { Readouts } from "@/components/Readouts";
import { SchematicKey } from "@/components/SchematicKey";
import { TestBench } from "@/components/TestBench";
import { Mode, SignalPath } from "@/components/SignalPath";
import { EXAMPLES } from "@/data/facts";
import { ApiError, generate } from "@/lib/api";
import { UiError, fmtDuration, toUiError } from "@/lib/errors";
import { RunRecord, claimFirstVisit, loadHistory, loadRemaining, pushHistory, saveRemaining } from "@/lib/history";
import { Replay, ReplayIndexEntry, loadIndex, loadReplay, play } from "@/lib/replay";
import { active, firstTokenMs, initialRun, runReducer } from "@/lib/runMachine";
import { SiteStatus, UNKNOWN, fetchStatus } from "@/lib/status";

export default function Playground() {
  const [run, dispatch] = useReducer(runReducer, initialRun);
  const [status, setStatus] = useState<SiteStatus>(UNKNOWN);
  const [mode, setMode] = useState<Mode>("live");
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const [replays, setReplays] = useState<ReplayIndexEntry[]>([]);
  const [replayId, setReplayId] = useState<string | null>(null);
  const [replayMeta, setReplayMeta] = useState<Replay | null>(null);
  const [history, setHistory] = useState<RunRecord[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [lastCode, setLastCode] = useState<string | null>(null);
  const [retryAt, setRetryAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const stopRef = useRef<() => void>(() => {});
  const cache = useRef(new Map<string, Replay>());

  const liveAllowed = status.live !== false;

  useEffect(() => {
    setHistory(loadHistory());
    setRemaining(loadRemaining());
    fetchStatus().then((s) => {
      setStatus(s);
      if (s.live === false) {
        // The live controls are about to be replaced; don't drop a keyboard user's focus on <body>.
        const hadFocus = document.getElementById("controls")?.contains(document.activeElement);
        setMode("replay");
        if (hadFocus) requestAnimationFrame(() => document.querySelector<HTMLElement>("#controls [aria-pressed=true]")?.focus());
      }
    });
    loadIndex()
      .then((ix) => { setReplays(ix); setReplayId((cur) => cur ?? ix[0]?.id ?? null); })
      .catch(() => setReplays([]));
    return () => stopRef.current();
  }, []);

  // 1 s clock for retry countdowns
  useEffect(() => {
    if (retryAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [retryAt]);

  const record = useCallback((r: RunRecord) => setHistory(pushHistory(r)), []);

  const runLive = useCallback(async () => {
    const ctl = new AbortController();
    const t0 = performance.now();
    const since = () => performance.now() - t0;
    const tick = setInterval(() => dispatch({ type: "tick", at: since() }), 100);
    let ttft: number | null = null;
    stopRef.current = () => ctl.abort();
    setRetryAt(null);
    dispatch({ type: "start", source: "live", prompt });
    const base = { at: new Date().toISOString(), source: "live" as const, prompt };
    try {
      await generate(prompt, {
        onOpen: () => dispatch({ type: "open" }),
        onToken: (t) => { const at = since(); ttft ??= at; dispatch({ type: "token", t, at }); },
        onDone: (info) => {
          dispatch({ type: "done", info, at: since() });
          setLastCode("ok");
          if (typeof info.remaining === "number") { saveRemaining(info.remaining); setRemaining(info.remaining); }
          record({ ...base, tokens: info.tokens, tok_s: info.tok_s, ttft_ms: ttft, outcome: info.finish_reason ?? "?" });
        },
      }, ctl.signal);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "protocol", String(e));
      if (err.code === "aborted") {
        dispatch({ type: "stop", at: since() });
        record({ ...base, tokens: null, tok_s: null, ttft_ms: ttft, outcome: "stopped" });
        return;
      }
      const ui = toUiError(err);
      dispatch({ type: "fail", error: ui, at: since() });
      setLastCode(err.code);
      record({ ...base, tokens: null, tok_s: null, ttft_ms: ttft, outcome: err.code });
      if (err.code === "daily_limit") { saveRemaining(0); setRemaining(0); }
      if (ui.retryAfterS) setRetryAt(Date.now() + ui.retryAfterS * 1000);
      if (ui.paused) {
        setStatus((s) => ({ ...s, live: false, note: s.note ?? (err.code === "disabled" ? "paused" : "unreachable") }));
        setMode("replay");
      }
    } finally {
      clearInterval(tick);
    }
  }, [prompt, record]);

  const runReplay = useCallback(async () => {
    if (!replayId) return;
    let rep = cache.current.get(replayId);
    if (!rep) {
      try {
        rep = await loadReplay(replayId);
        cache.current.set(replayId, rep);
      } catch {
        return;
      }
    }
    const r = rep;
    setReplayMeta(r);
    const t0 = performance.now();
    const tick = setInterval(() => dispatch({ type: "tick", at: performance.now() - t0 }), 100);
    dispatch({ type: "start", source: "replay", prompt: r.prompt, replayId: r.id });
    const cancel = play(r, {
      onOpen: () => dispatch({ type: "open" }),
      onToken: (t, at) => dispatch({ type: "token", t, at }),
      onDone: (d, at) => {
        clearInterval(tick);
        dispatch({ type: "done", info: d, at });
        record({ at: new Date().toISOString(), source: "replay", prompt: r.prompt, tokens: d.tokens, tok_s: d.tok_s,
                 ttft_ms: r.tokens[0]?.[1] ?? null, outcome: d.finish_reason ?? "?" });
      },
    });
    stopRef.current = () => {
      cancel();
      clearInterval(tick);
      dispatch({ type: "stop", at: performance.now() - t0 });
    };
  }, [replayId, record]);

  // First visit only: play the selected recording once, unasked, when the page settles in replay mode. Never a live
  // run (that spends quota), never with reduced motion, never if the visitor has already started something.
  const autoplayed = useRef(false);
  useEffect(() => {
    if (autoplayed.current || mode !== "replay" || status.live !== false || !replayId || run.phase !== "idle") return;
    autoplayed.current = true;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !claimFirstVisit()) return;
    runReplay();
  }, [mode, status.live, replayId, run.phase, runReplay]);

  // Bring the output into view if it is below the fold: the readouts on the wide layout, the listing once the
  // layout stacks (there the readouts are far from the code that is moving).
  const outRef = useRef<HTMLDivElement>(null);
  const showOutput = () => {
    const stacked = window.matchMedia("(max-width: 1000px)").matches;
    const el = stacked ? document.querySelector<HTMLElement>(".listing") : outRef.current;
    const r = el?.getBoundingClientRect();
    if (el && r && (r.top > window.innerHeight - 80 || r.bottom < 0)) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }
  };
  const watch = () => {
    if (!active(run)) {
      setMode("replay");
      runReplay();
    }
    showOutput();
  };

  const onRun = () => (mode === "live" ? runLive() : runReplay());
  const retryIn = retryAt !== null ? Math.max(0, Math.ceil((retryAt - now) / 1000)) : null;
  const err: UiError | null = run.phase === "error" ? run.error : null;

  return (
    <>
      <Head>
        <title>Codegen-1.5B · a fine-tuned code model</title>
      </Head>
      <main className="page">
        <Masthead page="schematic" />

        <Intro status={status} playing={active(run)} onWatch={watch} />

        {err && (
          <div className="banner" role="alert">
            <strong className="silk tp">{err.title}</strong>
            <span>{err.detail}</span>
            <span className="dim">code: {err.code}</span>
            <span className="act">
              {err.retryAfterS !== null && (
                <button type="button" className="btn-ghost silk" disabled={!!retryIn} onClick={() => runLive()}>
                  {retryIn ? `Retry in ${fmtDuration(retryIn)}` : "Retry"}
                </button>
              )}
              {err.offerReplay && mode === "live" && (
                <button type="button" className="btn-ghost silk" onClick={() => setMode("replay")}>Show recorded runs</button>
              )}
            </span>
          </div>
        )}

        {run.source === "replay" && run.phase !== "idle" && replayMeta && (
          <div className="banner info" role="status">
            <strong className="silk sig2">Replay</strong>
            <span>Recorded {replayMeta.recorded_at.slice(0, 16).replace("T", " ")} UTC on {replayMeta.endpoint}. Not generated now; no backend call.</span>
          </div>
        )}

        <SchematicKey />
        <div ref={outRef} className="anchor" aria-hidden="true" />
        <Readouts run={run} />

        <SignalPath
          run={run} mode={mode} liveAllowed={liveAllowed} onMode={setMode}
          prompt={prompt} onPrompt={setPrompt}
          replays={replays} replayId={replayId} onReplay={setReplayId}
          onRun={onRun} onStop={() => stopRef.current()}
          status={status} remaining={remaining} lastCode={lastCode}
        />

        <svg className={`route${active(run) ? " live" : ""}`} viewBox="0 0 1000 28" preserveAspectRatio="none" aria-hidden="true">
          <polyline className="wire" vectorEffect="non-scaling-stroke" points="935,0 935,13 70,13 70,28" />
          <polyline className="wire2" vectorEffect="non-scaling-stroke" points="950,0 950,20 86,20 86,28" />
        </svg>

        <div className="bottom">
          <div className="leftcol">
            <Listing run={run} onPlay={watch} />
            <TestBench run={run} />
          </div>
          <aside className="aside" aria-label="Evaluation, budget and run log">
            <EvalPanel />
            <BudgetPanel />
            <RunLog runs={history} />
            {firstTokenMs(run) !== null && run.source === "live" && firstTokenMs(run)! > 3000 && (
              <p className="note">TP1 above 3 s usually means this request paid a cold start (model load, 4–9 s).</p>
            )}
          </aside>
        </div>
        <Footer />
      </main>
    </>
  );
}
