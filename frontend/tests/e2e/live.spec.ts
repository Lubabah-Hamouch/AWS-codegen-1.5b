import { expect, test } from "@playwright/test";

// Opt-in (LIVE=1) and only meaningful with the kill switch OFF: one real cross-origin request from the deployed site.
// Accepts either a streamed result or a quota refusal; both prove CORS works and the JSON code is readable.
test.skip(!process.env.LIVE, "set LIVE=1 with the kill switch off");

test("live run from the deployed origin: streams, or shows a coded refusal", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one request is enough");
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/status of 429/.test(m.text())) errors.push(m.text()); });
  await page.goto("/");
  // replay is the default; the live request is the visitor's opt-in
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Try it live ▸" }).click(); // opens the prompt; nothing is sent yet
  await page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true }).click();
  const code = page.getByLabel("Generated code");
  const refusal = page.locator(".banner[role=alert]");
  await expect(code.or(refusal)).toBeVisible({ timeout: 30_000 });
  if (await refusal.isVisible()) {
    await expect(refusal).toContainText(/code: (daily_limit|daily_capacity|busy)/);
    await expect(refusal).not.toContainText("unreachable");
  } else {
    await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 60_000 });
  }
  await page.screenshot({ path: "test-results/live-desktop.png" });
  expect(errors).toEqual([]);
});
