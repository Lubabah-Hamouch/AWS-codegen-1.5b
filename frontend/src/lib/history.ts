// Per-browser memory: the run log and the last known quota. Storage can be unavailable (private windows, blocked
// site data); every access is guarded and the page works without it.

export type RunRecord = {
  at: string; // ISO
  source: "live" | "replay";
  prompt: string;
  tokens: number | null;
  tok_s: number | null;
  ttft_ms: number | null;
  outcome: string; // finish_reason or error code
};

const HISTORY = "cg.history";
const QUOTA = "cg.quota";
const VISITED = "cg.visited";
const MAX = 12;

function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* storage unavailable */
  }
}

export const loadHistory = (): RunRecord[] => read<RunRecord[]>(HISTORY, []).slice(0, MAX);

export function pushHistory(r: RunRecord): RunRecord[] {
  const next = [r, ...loadHistory()].slice(0, MAX);
  write(HISTORY, next);
  return next;
}

export const utcDay = (now = Date.now()) => new Date(now).toISOString().slice(0, 10);

/** Runs left today as last reported by the backend; null when unknown or from an earlier UTC day. */
export function loadRemaining(now = Date.now()): number | null {
  const q = read<{ day: string; remaining: number } | null>(QUOTA, null);
  return q && q.day === utcDay(now) ? q.remaining : null;
}

export function saveRemaining(remaining: number, now = Date.now()) {
  write(QUOTA, { day: utcDay(now), remaining });
}

/** Marks this browser as visited; true only the first time, and only if the mark could be stored (so a browser
 *  without storage is never treated as new on every load). */
export function claimFirstVisit(): boolean {
  try {
    if (localStorage.getItem(VISITED)) return false;
    localStorage.setItem(VISITED, "1");
    return localStorage.getItem(VISITED) === "1";
  } catch {
    return false;
  }
}
