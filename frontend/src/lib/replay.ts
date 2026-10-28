// Recorded runs: real outputs with real per-token timings from the deployed model (recorded by
// scripts/record_replays.py), replayed in the browser when live generation is unavailable or chosen.

import type { DoneInfo } from "./api";

export type ReplayIndexEntry = { id: string; title: string; prompt: string };

export type Replay = ReplayIndexEntry & {
  recorded_at: string; // ISO time of the recording
  endpoint: string; // what produced it, e.g. "lambda arm64 3008MB eu-north-1"
  first_byte_ms: number; // response headers arrived
  tokens: [string, number][]; // [text, ms since the request was sent]
  done_ms: number;
  done: DoneInfo;
};

export async function loadIndex(): Promise<ReplayIndexEntry[]> {
  const r = await fetch("/replays/index.json");
  if (!r.ok) throw new Error(`replay index: ${r.status}`);
  return r.json();
}

export async function loadReplay(id: string): Promise<Replay> {
  const r = await fetch(`/replays/${encodeURIComponent(id)}.json`);
  if (!r.ok) throw new Error(`replay ${id}: ${r.status}`);
  return r.json();
}

export type ReplayHandlers = {
  onOpen: () => void;
  onToken: (t: string, at: number) => void;
  onDone: (d: DoneInfo, at: number) => void;
};

/** Schedules the recorded events on their original offsets (scaled by `speed`). Returns a cancel function. */
export function play(rep: Replay, h: ReplayHandlers, speed = 1, timer: Pick<typeof globalThis, "setTimeout" | "clearTimeout"> = globalThis): () => void {
  const ids: ReturnType<typeof setTimeout>[] = [];
  const at = (ms: number, fn: () => void) => ids.push(timer.setTimeout(fn, ms / speed));
  at(rep.first_byte_ms, h.onOpen);
  for (const [t, ms] of rep.tokens) at(ms, () => h.onToken(t, ms));
  at(rep.done_ms, () => h.onDone(rep.done, rep.done_ms));
  return () => ids.forEach((i) => timer.clearTimeout(i));
}
