import { expect, test, type Page } from "@playwright/test";

// The plain-language on-ramp and the first-visit autoplay. Plain @playwright/test: every test here is a new visitor
// unless it marks itself as returning. Assumes the backend is parked (status.json live=false), like smoke.spec.ts.

const returning = (page: Page) => page.addInitScript(() => localStorage.setItem("cg.visited", "1"));
const idle = (page: Page) => expect(page.getByText(/^Nothing generated yet\./)).toBeVisible();

test("first visit: a recorded run plays once without a click, and the page does not scroll", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await expect(page.getByText("Live generation paused")).toBeVisible();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(1500);
  await idle(page);
  expect(errors).toEqual([]);
});

test("first visit with reduced motion: nothing plays by itself", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(1500);
  await idle(page);
});

test("intro: what it is, what to do and the result are in the first screen", async ({ page }) => {
  await returning(page);
  await page.goto("/");
  const inView = async (loc: ReturnType<Page["locator"]>) => {
    const b = await loc.boundingBox();
    return b !== null && b.y + b.height <= page.viewportSize()!.height;
  };
  const lead = page.getByRole("heading", { name: /fine-tuned to almost always answer in one clean, typed, documented function/ });
  const cta = page.getByRole("button", { name: "Watch a recorded run ▸" });
  await expect(lead).toBeVisible();
  await expect(cta).toBeVisible();
  await expect(page.getByRole("row", { name: /Clean answers .* 5\.5% 99\.4%/ })).toBeVisible();
  expect(await inView(lead)).toBe(true);
  expect(await inView(cta)).toBe(true);
  if (test.info().project.name === "desktop") expect(await inView(page.getByRole("row", { name: /Answer length/ }))).toBe(true);
  // phones: the decorative title block gives its space to the intro
  if (test.info().project.name === "mobile") await expect(page.locator(".tblock")).toBeHidden();
});

test("intro button plays a recorded run and brings the output into view", async ({ page }) => {
  await returning(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await idle(page);
  await page.getByRole("button", { name: "Watch a recorded run ▸" }).click();
  await expect(page.getByRole("button", { name: "Playing · see output ↓" })).toBeVisible();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  // wide layout: the readouts come into view; stacked layout: the listing itself
  await expect(page.locator(test.info().project.name === "desktop" ? ".readouts" : ".listing")).toBeInViewport();
  await expect(page.getByRole("button", { name: "Watch a recorded run ▸" })).toBeEnabled({ timeout: 15_000 });
});

test("before/after: the real base and shipped answers, verbatim, with their scores", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await returning(page);
  await page.goto("/");
  await expect(page.getByLabel("Base model answer")).toBeHidden();
  await page.getByText("Before / after: one real answer from the evaluation").click();
  const base = page.getByLabel("Base model answer");
  const shipped = page.getByLabel("Fine-tuned, as shipped answer");
  await expect(base).toContainText("To solve this problem, we need to first determine the length");
  await expect(base).toContainText("### Explanation:");
  await expect(shipped).toContainText("def prime_length(string: str) -> bool:");
  await expect(page.getByText("✓ passes HumanEval and HumanEval+")).toHaveCount(2);
  await expect(page.getByText(/✗ format: prose before the code, prose after the code, no docstring/)).toBeVisible();
  await expect(page.getByText("✓ format clean")).toBeVisible();
});

test("first visit on a phone: the play button leads to the output while it plays", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile");
  await page.goto("/");
  const cta = page.getByRole("button", { name: "Playing · see output ↓" });
  await expect(cta).toBeVisible({ timeout: 10_000 });
  await cta.click();
  await expect(page.locator(".listing")).toBeInViewport();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
});

test("schematic: each block says in plain words what it does; the key explains the labels", async ({ page }) => {
  await returning(page);
  await page.goto("/");
  for (const s of ["The fine-tuned model, running on AWS Lambda", "Decides whether a live request may run", "Runs checks on the generated code"])
    await expect(page.getByText(s)).toBeVisible();
  await expect(page.getByText("Live measurements of the current run")).toBeHidden();
  await page.getByText("How to read the schematic").click();
  await expect(page.getByText("TP1–TP4 · test points")).toBeVisible();
  await expect(page.getByText("Live measurements of the current run")).toBeVisible();
});

test("empty listing invites a run and its button plays one", async ({ page }) => {
  await returning(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("play a run first: checks run on the finished listing")).toBeVisible();
  await page.getByRole("button", { name: "Play a recorded run ▸" }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Play a recorded run ▸" })).toHaveCount(0);
});

test("link preview: description, Open Graph card and its image", async ({ page, request }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("/");
  const meta = (sel: string) => page.locator(sel).getAttribute("content");
  expect(await meta('meta[name="description"]')).toMatch(/almost always answer in one clean, typed, documented Python function/);
  expect(await meta('meta[property="og:title"]')).toBe("Codegen-1.5B: a fine-tuned code model, deployed to AWS for $0");
  expect(await meta('meta[name="twitter:card"]')).toBe("summary_large_image");
  const img = await meta('meta[property="og:image"]');
  expect(img).toMatch(/^https:\/\/.+\/og\.png$/);
  // the image as this server serves it (the absolute URL points at the deployed site)
  const r = await request.get("/og.png");
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toBe("image/png");
});
