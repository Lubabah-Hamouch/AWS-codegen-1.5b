// Maps backend codes (and client-side failures) to what the UI says and does. Branch on `code`, never on message text.

import type { ApiError } from "./api";

export type UiError = {
  code: string;
  title: string;
  detail: string;
  /** retry the same request after this many seconds (busy) */
  retryAfterS: number | null;
  /** live generation is not possible right now; offer the recorded runs */
  offerReplay: boolean;
  /** live generation is off for this session (paused/unreachable), not just this request */
  paused: boolean;
};

export function secondsToUtcMidnight(now = Date.now()): number {
  return 86400 - Math.floor(now / 1000) % 86400;
}

export function fmtDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h} h ${m} min` : m ? `${m} min` : `${Math.max(1, Math.round(s))} s`;
}

export function toUiError(e: ApiError, now = Date.now()): UiError {
  const base = { code: e.code, retryAfterS: null, offerReplay: false, paused: false };
  const reset = `resets 00:00 UTC, in ${fmtDuration(secondsToUtcMidnight(now))}`;
  switch (e.code) {
    case "busy":
      return { ...base, title: "Both generation slots are in use", detail: "Someone else is generating. Retrying shortly is fine.",
               retryAfterS: e.retryAfterS ?? 2 };
    case "daily_limit":
      return { ...base, title: "You've used today's live runs", detail: `The limit is 5 per day per visitor; it ${reset}. Recorded runs still work.`,
               offerReplay: true };
    case "daily_capacity":
      return { ...base, title: "Today's shared budget is spent", detail: `The whole site gets a fixed number of live runs a day to stay at $0; it ${reset}. Recorded runs still work.`,
               offerReplay: true };
    case "disabled":
      return { ...base, title: "Live generation is paused", detail: "The backend's kill switch is on. Showing recorded runs instead.",
               offerReplay: true, paused: true };
    case "starting":
      return { ...base, title: "The model is still loading", detail: "A cold start takes 4–9 s. Retry in a moment.", retryAfterS: e.retryAfterS ?? 5 };
    case "unavailable":
    case "network":
    case "http_403":
      return { ...base, title: "The backend is unreachable", detail: "It may be paused or failing closed. Showing recorded runs instead.",
               offerReplay: true, paused: true };
    case "bad_request":
    case "too_large":
      return { ...base, title: "The request was rejected", detail: e.message };
    case "generation_failed":
    case "protocol":
      return { ...base, title: "Generation failed partway", detail: "The output so far is kept. Running it again usually works." };
    case "aborted":
      return { ...base, title: "Stopped", detail: "You stopped the run; the slot was released." };
    default:
      return { ...base, title: `Unexpected response (${e.status || "no status"})`, detail: e.message };
  }
}
