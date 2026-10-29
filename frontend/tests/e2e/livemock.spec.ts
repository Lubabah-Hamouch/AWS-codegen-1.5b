import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { expect, test, type Page, type Route } from "./fixtures";

// Live mode against a simulated backend: status.json and POST /generate are intercepted in the browser, so this never
// reaches AWS and is safe against the deployed site. Covers the cold-start wait, the "starting" retry, the timeout
// fallback and the out-of-quota fallback.

const rep = JSON.parse(readFileSync("public/replays/fibonacci.json", "utf8")); // run from frontend/, like the config
const SSE = rep.tokens.map(([t]: [string]) => `event: token\ndata: ${JSON.stringify({ t })}\n\n`).join("")
  + `event: done\ndata: ${JSON.stringify({ ...rep.done, remaining: 4 })}\n\n`;

const cors = (r: Route) => ({ "access-control-allow-origin": r.request().headers()["origin"] ?? "*",
  "access-control-allow-headers": "content-type", "access-control-expose-headers": "retry-after" });
const stream = (r: Route) => r.fulfill({ status: 200, headers: { ...cors(r), "content-type": "text/event-stream" }, body: SSE });
const refuse = (r: Route, status: number, code: string, retry?: string) => r.fulfill({ status,
  headers: { ...cors(r), "content-type": "application/json", ...(retry ? { "retry-after": retry } : {}) },
  body: JSON.stringify({ error: code, code }) });

async function live(page: Page, generate: (r: Route) => unknown) {
  await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: '{"live": true, "since": "x", "note": "live"}' }));
  await page.route("**/generate", (r) => (r.request().method() === "OPTIONS" ? r.fulfill({ status: 204, headers: cors(r) }) : generate(r)));
  await page.goto("/");
  // replay stays the default even with the backend on; live is the visitor's choice
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Live", exact: true }).click();
}
const run = (page: Page) => page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true });

test("cold start: the wait says the model is waking up, wherever the visitor is looking", async ({ page }) => {
  // held 8 s: the notice appears 1.5 s in, so a loaded machine still has a wide margin (4 s once flaked under load)
  await live(page, async (r) => { await new Promise((ok) => setTimeout(ok, 8000)); await stream(r); });
  await run(page).click();
  const status = page.locator("#controls").getByText(/waking up the model… \d+ s \(usually 5–10 s\)/);
  await expect(status).toBeVisible({ timeout: 6000 });
  await expect(status).toBeInViewport(); // next to the button, so a phone visitor sees it too
  await expect(page.locator("#u3")).toContainText("waking up");
  await expect(page.locator("#u3")).not.toContainText("prefill");
  await expect(page.getByText(/^Waking up the model… The first request after a quiet spell/)).toBeAttached();
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#u3")).toContainText("idle");
});

test("503 starting is retried by itself; no error, no click", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  let calls = 0;
  await live(page, (r) => (++calls === 1 ? refuse(r, 503, "starting", "1") : stream(r)));
  await run(page).click();
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  expect(calls).toBe(2);
  await expect(page.locator(".banner[role=alert]")).toHaveCount(0);
});

test("no response by the deadline: a clear message and a replay, not an endless wait", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.clock.install();
  await live(page, () => new Promise(() => {})); // never answers
  await run(page).click();
  await page.clock.runFor(96_000);
  const banner = page.locator(".banner[role=alert]");
  await expect(banner).toContainText("The model took too long to wake up");
  await banner.getByRole("button", { name: "Show recorded runs" }).click();
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("quota used up: Run is replaced in place by the reset time and a replay button", async ({ page }) => {
  await live(page, (r) => refuse(r, 429, "daily_limit", "3600"));
  await run(page).click();
  const blocked = page.locator("#controls .blocked");
  await expect(blocked).toContainText(/No live runs left today · resets in \d+ (h|min)/);
  await expect(blocked).toBeInViewport();
  await expect(run(page)).toHaveCount(0);
  await expect(page.locator(".banner[role=alert]")).toHaveCount(0);
  // the intro's "Try it live" becomes the same reset time, next to its replay button
  await expect(page.locator(".intro")).toContainText(/No live runs left today · resets in/);
  await expect(page.getByRole("button", { name: "Try it live ▸" })).toHaveCount(0);
  // still blocked after a reload (the count is remembered for the UTC day); the page reopens in replay mode, so the
  // reset time stands where "Try it live" was, next to the intro's replay button
  await page.reload();
  await expect(page.locator(".intro")).toContainText(/No live runs left today · resets in/);
  await expect(page.getByRole("button", { name: "Try it live ▸" })).toHaveCount(0);
  await page.locator(".intro").getByRole("button", { name: "Watch a recorded run ▸" }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
});

test("Try it live: replay stays the default; the button opens the prompt and Run sends one request", async ({ page }) => {
  let calls = 0;
  await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: '{"live": true, "since": "x", "note": "live"}' }));
  await page.route("**/generate", (r) => (r.request().method() === "OPTIONS" ? r.fulfill({ status: 204, headers: cors(r) }) : (calls++, stream(r))));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Live generation is on")).toBeVisible();
  for (const theme of ["soldermask", "datasheet"]) {  // the live-only intro controls, audited in a dark and the light theme
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    const r = await new AxeBuilder({ page }).include(".intro").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(r.violations.map((v) => `${theme} ${v.id}: ${v.nodes[0]?.target}`)).toEqual([]);
  }
  await page.waitForTimeout(500);
  expect(calls).toBe(0); // nothing live happens by itself
  await page.getByRole("button", { name: "Try it live ▸" }).click();
  await expect(page.locator("#spec")).toBeFocused(); // the prompt box, ready for a choice
  await page.waitForTimeout(1000);
  expect(calls).toBe(0); // choosing live sends nothing
  await page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  expect(calls).toBe(1);
  await expect(page.getByRole("button", { name: "Live", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("paused backend: no Try it live button at all", async ({ page }) => {
  await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: '{"live": false, "since": "x", "note": "paused"}' }));
  await page.goto("/");
  await expect(page.getByText("Live generation paused")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try it live ▸" })).toHaveCount(0);
});

test("a typing name used but not imported: the import is added, marked, and used by the test bench", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  const answer = "```python\nfrom typing import List\n\n\ndef transpose(matrix: Tuple[Tuple[int, ...], ...]) -> List[Tuple[int, ...]]:\n"
    + "    \"\"\"Transpose a matrix.\"\"\"\n    return list(zip(*matrix))\n```";
  const sse = answer.split(/(?<=\n)/).map((t) => `event: token\ndata: ${JSON.stringify({ t })}\n\n`).join("")
    + `event: done\ndata: ${JSON.stringify({ finish_reason: "stop", tokens: 40, prompt_tokens: 20, tok_s: 15, ttft_s: 0.4, prompt_version: "generate.v1", remaining: 4 })}\n\n`;
  await live(page, (r) => r.fulfill({ status: 200, headers: { ...cors(r), "content-type": "text/event-stream" }, body: sse }));
  await page.locator("#spec").fill("Write a function that transposes a matrix given as a tuple of tuples.");
  await run(page).click();
  const code = page.getByLabel("Generated code");
  await expect(code).toContainText("from typing import List, Tuple", { timeout: 15_000 });
  await expect(page.locator(".listing-foot")).toContainText("+ L1 import added after generation: Tuple used in a type hint but not imported");
  await expect(page.locator(".code .gutter")).toContainText("+1");
  // the test bench runs the served code: it defines transpose instead of failing with NameError
  await page.getByRole("button", { name: "Run code ▸" }).click();
  await expect(page.locator(".bench-sum")).not.toContainText("NameError", { timeout: 90_000 });
  await expect(page.locator(".bench-sum")).toContainText(/transpose/, { timeout: 90_000 });
});

test("nothing is sent until Run: load, the Live toggle, examples and Try it live send no request", async ({ page }) => {
  const sent: string[] = [];
  await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: '{"live": true, "since": "x", "note": "live"}' }));
  await page.route("**/generate", (r) => {
    if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: cors(r) });
    sent.push(JSON.parse(r.request().postData() ?? "{}").prompt);
    return stream(r);
  });
  await page.goto("/");
  await expect(page.getByText("Live generation is on")).toBeVisible();
  await page.getByRole("button", { name: "Live", exact: true }).click();
  await page.locator("#controls .chips button").nth(1).click(); // the palindrome example
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  await page.getByRole("button", { name: "Try it live ▸" }).click();
  await expect(page.locator("#spec")).toBeFocused();
  await page.waitForTimeout(2000);
  expect(sent).toEqual([]);
  await page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true }).click(); // the one explicit send
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatch(/palindrome/); // the example the visitor picked, not a default
});
