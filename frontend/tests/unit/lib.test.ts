import { describe, expect, it, vi } from "vitest";
import { ApiError, generate } from "@/lib/api";
import { fmtDuration, secondsToUtcMidnight, toUiError } from "@/lib/errors";
import { extractCode, suggestFilename, tokenize, unusedImports } from "@/lib/python";
import { play, type Replay } from "@/lib/replay";
import { initialRun, liveRate, rateSeries, runReducer } from "@/lib/runMachine";
import { SSEParser } from "@/lib/sse";
import { fetchStatus } from "@/lib/status";
import { nextTheme, THEMES } from "@/lib/themes";

const FIB = '```python\nfrom typing import List\n\ndef fibonacci(n: int) -> int:\n    """Return the nth Fibonacci number."""\n    if n <= 1:\n        return n\n    return fibonacci(n - 1) + fibonacci(n - 2)\n```';

describe("SSEParser", () => {
  it("parses events split at arbitrary byte boundaries", () => {
    const wire = 'event: token\ndata: {"t": "def"}\n\nevent: token\r\ndata: {"t": " f"}\r\n\r\n: comment\n\nevent: done\ndata: {"finish_reason": "stop"}\n\n';
    for (let cut = 1; cut < wire.length; cut += 7) {
      const p = new SSEParser();
      const got = [...p.feed(wire.slice(0, cut)), ...p.feed(wire.slice(cut))];
      expect(got.map((m) => m.event)).toEqual(["token", "token", "done"]);
      expect(JSON.parse(got[1].data).t).toBe(" f");
    }
  });
  it("joins multi-line data", () => {
    expect(new SSEParser().feed("data: a\ndata: b\n\n")).toEqual([{ event: "message", data: "a\nb" }]);
  });
});

function sseResponse(body: string, init: ResponseInit = { status: 200 }) {
  return new Response(new Blob([body]).stream(), { ...init, headers: { "content-type": "text/event-stream", ...(init.headers ?? {}) } });
}

describe("generate()", () => {
  it("streams tokens then done", async () => {
    const f = vi.fn(async () => sseResponse('event: token\ndata: {"t": "a"}\n\nevent: token\ndata: {"t": "b"}\n\nevent: done\ndata: {"finish_reason": "stop", "tokens": 2, "remaining": 4}\n\n'));
    const toks: string[] = [];
    let done: unknown = null;
    await generate("p", { onToken: (t) => toks.push(t), onDone: (d) => (done = d) }, new AbortController().signal, f as unknown as typeof fetch);
    expect(toks).toEqual(["a", "b"]);
    expect(done).toMatchObject({ finish_reason: "stop", remaining: 4 });
  });
  it("maps a JSON refusal to its code and retry-after", async () => {
    const f = async () => new Response(JSON.stringify({ error: "busy, retry shortly", code: "busy" }), { status: 429, headers: { "retry-after": "2" } });
    const e = await generate("p", { onToken() {}, onDone() {} }, new AbortController().signal, f as unknown as typeof fetch).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.retryAfterS]).toEqual([429, "busy", 2]);
  });
  it("treats a fetch failure (CORS-less 403, offline) as network", async () => {
    const f = async () => { throw new TypeError("Failed to fetch"); };
    const e = await generate("p", { onToken() {}, onDone() {} }, new AbortController().signal, f as unknown as typeof fetch).catch((x) => x);
    expect(e.code).toBe("network");
    expect(toUiError(e).paused).toBe(true);
  });
  it("flags a stream that ends without done", async () => {
    const f = async () => sseResponse('event: token\ndata: {"t": "a"}\n\n');
    const e = await generate("p", { onToken() {}, onDone() {} }, new AbortController().signal, f as unknown as typeof fetch).catch((x) => x);
    expect(e.code).toBe("protocol");
  });
  it("surfaces a mid-stream error event", async () => {
    const f = async () => sseResponse('event: token\ndata: {"t": "a"}\n\nevent: error\ndata: {"error": "generation failed", "code": "generation_failed"}\n\n');
    const e = await generate("p", { onToken() {}, onDone() {} }, new AbortController().signal, f as unknown as typeof fetch).catch((x) => x);
    expect(e.code).toBe("generation_failed");
  });
});

describe("errors", () => {
  it("covers every backend code with a non-generic message", () => {
    for (const code of ["busy", "daily_limit", "daily_capacity", "disabled", "unavailable", "starting", "bad_request", "too_large", "generation_failed"]) {
      expect(toUiError(new ApiError(429, code, "m")).title).not.toMatch(/^Unexpected/);
    }
  });
  it("offers replays for quota and pause, retry for busy", () => {
    expect(toUiError(new ApiError(429, "daily_limit", "")).offerReplay).toBe(true);
    expect(toUiError(new ApiError(503, "disabled", "")).paused).toBe(true);
    expect(toUiError(new ApiError(429, "busy", "", 3)).retryAfterS).toBe(3);
  });
  it("counts to UTC midnight", () => {
    expect(secondsToUtcMidnight(Date.UTC(2026, 9, 28, 23, 0, 0))).toBe(3600);
    expect(fmtDuration(3900)).toBe("1 h 5 min");
  });
});

describe("run reducer", () => {
  it("goes connecting → streaming → done and ignores late events", () => {
    let s = runReducer(initialRun, { type: "start", source: "live", prompt: "p" });
    expect(s.phase).toBe("connecting");
    s = runReducer(s, { type: "token", t: "a", at: 600 });
    s = runReducer(s, { type: "token", t: "b", at: 700 });
    s = runReducer(s, { type: "token", t: "c", at: 800 });
    expect([s.phase, s.text]).toEqual(["streaming", "abc"]);
    expect(liveRate(s)).toBeCloseTo(10);
    s = runReducer(s, { type: "done", info: { finish_reason: "stop", tokens: 3, prompt_tokens: 1, tok_s: 9.9, ttft_s: 0.5, prompt_version: "v" }, at: 900 });
    expect(s.phase).toBe("done");
    expect(runReducer(s, { type: "token", t: "x", at: 1000 }).text).toBe("abc");
  });
  it("computes a rolling rate series", () => {
    expect(rateSeries([0, 100, 200, 300, 400, 500, 600, 700], 6)).toEqual([10, 10]);
  });
});

describe("python helpers", () => {
  it("extracts the fenced code, also mid-stream", () => {
    expect(extractCode(FIB).startsWith("from typing")).toBe(true);
    expect(extractCode(FIB).includes("```")).toBe(false);
    expect(extractCode("```python\ndef f(")).toBe("def f(");
  });
  it("highlights keywords, def names and docstrings, losslessly", () => {
    const code = extractCode(FIB);
    const toks = tokenize(code);
    expect(toks.map((t) => t.v).join("")).toBe(code);
    expect(toks.find((t) => t.k === "def")?.v).toBe("fibonacci");
    expect(toks.some((t) => t.k === "doc")).toBe(true);
    expect(tokenize('x = "unterminated').map((t) => t.v).join("")).toBe('x = "unterminated');
  });
  it("notes the unused import the model actually emits", () => {
    expect(unusedImports(extractCode(FIB))).toEqual([{ line: 1, text: "unused import List" }]);
    expect(unusedImports("import math\nprint(math.pi)")).toEqual([]);
  });
  it("names the file after the first def", () => {
    expect(suggestFilename(extractCode(FIB))).toBe("fibonacci.py");
    expect(suggestFilename("x = 1")).toBe("generated.py");
  });
});

describe("replay", () => {
  it("schedules tokens on their recorded offsets", () => {
    vi.useFakeTimers();
    const rep: Replay = {
      id: "r", title: "r", prompt: "p", recorded_at: "", endpoint: "", first_byte_ms: 50,
      tokens: [["a", 400], ["b", 500]], done_ms: 550,
      done: { finish_reason: "stop", tokens: 2, prompt_tokens: 1, tok_s: 10, ttft_s: 0.3, prompt_version: "v" },
    };
    const seen: string[] = [];
    const cancel = play(rep, { onOpen: () => seen.push("open"), onToken: (t, at) => seen.push(`${t}@${at}`), onDone: () => seen.push("done") });
    vi.advanceTimersByTime(450);
    expect(seen).toEqual(["open", "a@400"]);
    cancel();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual(["open", "a@400"]);
    vi.useRealTimers();
  });
});

describe("status and themes", () => {
  it("reads status.json and degrades to unknown", async () => {
    expect(await fetchStatus((async () => new Response('{"live": false, "since": "t", "note": "paused"}')) as unknown as typeof fetch))
      .toEqual({ live: false, since: "t", note: "paused" });
    expect((await fetchStatus((async () => new Response("", { status: 404 })) as unknown as typeof fetch)).live).toBeNull();
    expect((await fetchStatus((async () => { throw new Error("x"); }) as unknown as typeof fetch)).live).toBeNull();
  });
  it("has four presets, soldermask first, cycling", () => {
    expect(THEMES.map((t) => t.id)).toEqual(["soldermask", "instrument", "tty", "datasheet"]);
    expect(nextTheme("datasheet")).toBe("soldermask");
  });
});
