// One run (live or replayed) as a reducer. Times are ms since the run started (performance.now based for live runs,
// the recorded offsets for replays), so both sources drive the same readouts.

import type { DoneInfo } from "./api";
import type { UiError } from "./errors";

export type Phase = "idle" | "connecting" | "streaming" | "done" | "error" | "stopped";
export type Source = "live" | "replay";

export type RunState = {
  phase: Phase;
  source: Source;
  prompt: string;
  text: string;
  tokenTimes: number[]; // arrival offset of each token event, ms
  elapsedMs: number;
  done: DoneInfo | null;
  error: UiError | null;
  replayId: string | null;
};

export type RunAction =
  | { type: "start"; source: Source; prompt: string; replayId?: string }
  | { type: "open" }
  | { type: "token"; t: string; at: number }
  | { type: "tick"; at: number }
  | { type: "done"; info: DoneInfo; at: number }
  | { type: "fail"; error: UiError; at: number }
  | { type: "stop"; at: number }
  | { type: "reset" };

export const initialRun: RunState = {
  phase: "idle", source: "live", prompt: "", text: "", tokenTimes: [], elapsedMs: 0, done: null, error: null, replayId: null,
};

export function runReducer(s: RunState, a: RunAction): RunState {
  switch (a.type) {
    case "start":
      return { ...initialRun, phase: "connecting", source: a.source, prompt: a.prompt, replayId: a.replayId ?? null };
    case "open":
      return s.phase === "connecting" ? { ...s, phase: "streaming" } : s;
    case "token":
      if (!active(s)) return s;
      return { ...s, phase: "streaming", text: s.text + a.t, tokenTimes: [...s.tokenTimes, a.at], elapsedMs: a.at };
    case "tick":
      return active(s) ? { ...s, elapsedMs: Math.max(s.elapsedMs, a.at) } : s;
    case "done":
      return active(s) ? { ...s, phase: "done", done: a.info, elapsedMs: a.at } : s;
    case "fail":
      return active(s) ? { ...s, phase: "error", error: a.error, elapsedMs: a.at } : s;
    case "stop":
      return active(s) ? { ...s, phase: "stopped", elapsedMs: a.at } : s;
    case "reset":
      return initialRun;
  }
}

export const active = (s: RunState) => s.phase === "connecting" || s.phase === "streaming";

/** Client-observed time to first token, ms (includes network and any cold start, unlike the server's ttft_s). */
export const firstTokenMs = (s: RunState) => (s.tokenTimes.length ? s.tokenTimes[0] : null);

/** Decode rate over the token events seen so far (excludes the wait for the first token). */
export function liveRate(s: RunState): number | null {
  const t = s.tokenTimes;
  if (t.length < 3) return null;
  const span = (t[t.length - 1] - t[0]) / 1000;
  return span > 0 ? (t.length - 1) / span : null;
}

/** Rolling rate per token (window of `w` events) for the trace. */
export function rateSeries(times: number[], w = 6): number[] {
  const out: number[] = [];
  for (let i = w; i < times.length; i++) {
    const span = (times[i] - times[i - w]) / 1000;
    if (span > 0) out.push(w / span);
  }
  return out;
}
