import { expect, test } from "./fixtures";

// The real UI against the real backend while the Function URL stays locked to the public. Opt-in: PRIVATE_PROXY points
// at infra/scripts/signing_proxy.py, which signs the browser's requests with the operator's credentials; the app kill
// switch must be off (seed_state.py --kill off --no-status, so status.json keeps telling visitors "paused").
// status.json is answered here with live=true so the page offers Try it live.
test.skip(!process.env.PRIVATE_PROXY, "set PRIVATE_PROXY with the signing proxy running and the app kill switch off");

test("Try it live, end to end against the real model: streams, finishes cleanly, checks pass", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one real generation is enough");
  test.setTimeout(180_000);
  const proxy = process.env.PRIVATE_PROXY!;
  let sent = 0;
  await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: '{"live": true, "since": "x", "note": "live"}' }));
  await page.route("**/generate", async (r) => {
    if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" } });
    sent++;
    const resp = await r.fetch({ url: `${proxy}/generate`, timeout: 120_000 });
    await r.fulfill({ response: resp, headers: { ...resp.headers(), "access-control-allow-origin": r.request().headers()["origin"] ?? "*" } });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Try it live ▸" }).click(); // opens the prompt; nothing is sent yet
  expect(sent).toBe(0);
  await page.locator("#controls").getByRole("button", { name: "Run ▸", exact: true }).click();
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 150_000 });
  expect(sent).toBe(1);
  await expect(page.getByLabel("Generated code")).toContainText("def fibonacci");
  await expect(page.getByText("server-measured")).toBeVisible();
  await expect(page.locator("#controls")).toContainText(/\d \/ 5 left/); // the backend's remaining count, shown in U2/U1
  await page.screenshot({ path: "test-results/private-live-done.png", fullPage: true });
  await page.getByRole("button", { name: "Run checks ▸" }).click();
  await expect(page.locator(".bench-sum")).toBeVisible({ timeout: 90_000 });
  console.log("test bench:", (await page.locator(".bench-sum").innerText()).replace(/\s+/g, " "));
});
