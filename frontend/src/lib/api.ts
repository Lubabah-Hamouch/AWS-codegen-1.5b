// Client for POST /generate on the Lambda Function URL (see backend/app/main.py for the contract).

import { SSEParser } from "./sse";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
export const MAX_PROMPT_CHARS = 2000;
export const MAX_TOKENS = 512;

export type DoneInfo = {
  finish_reason: string | null;
  tokens: number | null;
  prompt_tokens: number | null;
  tok_s: number | null;
  ttft_s: number | null;
  prompt_version: string;
  remaining?: number | null;
};

/** A refusal or failure. `code` is the backend's stable code, or a client-side one: network, aborted, protocol. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS: number | null = null,
  ) {
    super(message);
  }
}

export type StreamHandlers = {
  onOpen?: () => void;
  onToken: (text: string) => void;
  onDone: (info: DoneInfo) => void;
};

export async function generate(prompt: string, h: StreamHandlers, signal: AbortSignal, fetchImpl: typeof fetch = fetch) {
  let res: Response;
  try {
    res = await fetchImpl(`${API_URL}/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt, max_tokens: MAX_TOKENS }),
      signal,
    });
  } catch (e) {
    if (signal.aborted) throw new ApiError(0, "aborted", "stopped");
    // DNS, offline, or a response without CORS headers: the latter is what an AWS_IAM-locked Function URL (the
    // out-of-band kill switch) looks like from a browser. Treated as "unavailable".
    throw new ApiError(0, "network", "the backend could not be reached");
  }
  if (!res.ok) {
    let body: { error?: string; code?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body (e.g. AWS's own 403) */
    }
    const ra = Number(res.headers.get("retry-after"));
    throw new ApiError(res.status, body.code ?? `http_${res.status}`, body.error ?? res.statusText, Number.isFinite(ra) && ra > 0 ? ra : null);
  }
  if (!res.body) throw new ApiError(0, "protocol", "empty response");
  h.onOpen?.();

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SSEParser();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const m of parser.feed(value)) {
        const d = JSON.parse(m.data);
        if (m.event === "token") h.onToken(d.t);
        else if (m.event === "done") return h.onDone(d as DoneInfo);
        else if (m.event === "error") throw new ApiError(200, d.code ?? "generation_failed", d.error ?? "generation failed");
      }
    }
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (signal.aborted) throw new ApiError(0, "aborted", "stopped");
    throw new ApiError(0, "network", "the stream was interrupted");
  }
  throw new ApiError(0, "protocol", "the stream ended without a done event");
}
