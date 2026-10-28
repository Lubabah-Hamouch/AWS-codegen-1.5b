import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Runs real Python (Pyodide) in the browser under the site's real CSP. Replay mode (backend parked).

async function replay(page: Page, title: string) {
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
  await page.getByRole("button", { name: title, exact: true }).click();
  await page.getByRole("button", { name: "Replay ▸" }).click();
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 20_000 });
}

test.describe.configure({ timeout: 120_000 });

test("nothing of Python loads until the bench is used", async ({ page }) => {
  const py: string[] = [];
  page.on("request", (r) => {
    if (/pyodide|testbench\.worker/.test(r.url())) py.push(r.url());
  });
  await page.goto("/");
  await replay(page, "fibonacci");
  expect(py).toEqual([]);
});

test("fibonacci replay: hand-written checks run in the browser and pass", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await replay(page, "fibonacci");
  await page.getByRole("button", { name: "Run checks ▸" }).click();
  const sum = page.locator(".bench-sum");
  await expect(sum).toContainText("✓ 5/5 checks pass", { timeout: 90_000 });
  await expect(sum).toContainText("fibonacci()");
  await expect(page.locator(".bench-tbl tbody tr")).toHaveCount(5);
  await expect(page.locator(".bench")).toContainText("Hand-written checks for this one example prompt; assumes F(0) = 0");
  await page.locator(".leftcol").screenshot({ path: "test-results/bench-pass.png" });
  expect(errors).toEqual([]);
  const axe = await new AxeBuilder({ page }).include(".bench").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(axe.violations.map((v) => v.id)).toEqual([]);
});

test("merge_intervals replay: the model's real bug shows as failed checks", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("/");
  await replay(page, "merge_intervals");
  await page.getByRole("button", { name: "Run checks ▸" }).click();
  await expect(page.locator(".bench-sum")).toContainText("✗ 2/5 checks pass", { timeout: 90_000 });
  await expect(page.locator(".bench-tbl")).toContainText("TypeError: 'tuple' object does not support item assignment");
  await page.locator(".leftcol").screenshot({ path: "test-results/bench-fail.png" });
});

test("partial output gets a behavioural report, never pass/fail", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
  await page.getByRole("button", { name: "Replay ▸" }).click();
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci", { timeout: 15_000 });
  await page.getByRole("button", { name: "Stop ■" }).click();
  await page.getByRole("button", { name: "Run code ▸" }).click();
  const sum = page.locator(".bench-sum");
  await expect(sum).toBeVisible({ timeout: 90_000 });
  await expect(sum).not.toContainText(/checks pass|✓|✗/);
  await expect(page.locator(".bench-tbl")).toHaveCount(0);
});

test("a runaway loop in the worker is still running at the limit and is killed", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("/");
  const r = await page.evaluate(async () => {
    const w = new Worker("/testbench.worker.mjs", { type: "module" });
    await new Promise<void>((res, rej) => {
      w.onmessage = (e) => (e.data.type === "ready" ? res() : rej(e.data));
    });
    let answered = false;
    w.onmessage = () => {
      answered = true;
    };
    w.postMessage({ code: "while True:\n    pass\n", suite: null });
    await new Promise((res) => setTimeout(res, 5500));
    w.terminate();
    const t0 = performance.now();
    await new Promise((res) => setTimeout(res, 50));
    return { answered, pageResponsive: performance.now() - t0 < 1000 };
  });
  expect(r).toEqual({ answered: false, pageResponsive: true });
});
