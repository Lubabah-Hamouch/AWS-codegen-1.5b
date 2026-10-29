import { expect, test, type Page } from "./fixtures";

// Assumes the backend is parked (status.json live=false): exercises replay mode, which costs no invocation.

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

test("the real status.json is served uncached and says live or paused", async ({ request }) => {
  const r = await request.get("/status.json");
  expect(r.status()).toBe(200);
  const s = await r.json();
  expect(typeof s.live).toBe("boolean");
  expect(["live", "paused", "circuit breaker"]).toContain(s.note);
});

test("paused backend: banner, replay plays a real recorded run, no CSP or console errors", async ({ page }, info) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Codegen");
  await expect(page.getByText("Live generation paused")).toBeVisible();
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Replay ▸" }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Recorded .* UTC on Lambda arm64/)).toBeVisible();
  await page.screenshot({ path: `test-results/home-${info.project.name}.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test("theme picker applies and persists a preset", async ({ page }, info) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "soldermask");
  await page.getByRole("button", { name: "Theme: Soldermask" }).click();
  await page.getByRole("menuitemradio", { name: /Datasheet/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "datasheet");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "datasheet");
  await page.screenshot({ path: `test-results/home-datasheet-${info.project.name}.png` });
  await page.keyboard.press("Shift+T");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "soldermask");
});

test("notes page renders the datasheet without errors", async ({ page }, info) => {
  const errors = watchErrors(page);
  await page.goto("/notes/");
  await expect(page.getByRole("heading", { name: /Evaluation/ })).toBeVisible();
  await expect(page.getByText("64.0% (105/164)")).toBeVisible();
  await page.screenshot({ path: `test-results/notes-${info.project.name}.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test("no horizontal page scroll", async ({ page }) => {
  for (const path of ["/", "/notes/"]) {
    await page.goto(path);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(over, path).toBeLessThanOrEqual(0);
  }
});

test("unknown path gets the 404 page", async ({ page }) => {
  const r = await page.goto("/nope/");
  expect(r?.status()).toBe(404);
  await expect(page.getByText("Open circuit")).toBeVisible();
});
