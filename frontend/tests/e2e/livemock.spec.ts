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
  await expect(page.getByRole("button", { name: "Live", exact: true })).toHaveAttribute("aria-pressed", "true");
}
const run = (page: Page) => page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true });

test("cold start: the wait says the model is waking up, wherever the visitor is looking", async ({ page }) => {
  await live(page, async (r) => { await new Promise((ok) => setTimeout(ok, 4000)); await stream(r); });
  await run(page).click();
  const status = page.locator("#controls").getByText(/waking up the model… \d+ s \(usually 5–10 s\)/);
  await expect(status).toBeVisible({ timeout: 3000 });
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
  // still blocked after a reload (the count is remembered for the UTC day)
  await page.reload();
  await expect(page.locator("#controls .blocked")).toBeVisible();
  await page.locator("#controls .blocked").getByRole("button", { name: "Watch a recorded run ▸" }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
});
