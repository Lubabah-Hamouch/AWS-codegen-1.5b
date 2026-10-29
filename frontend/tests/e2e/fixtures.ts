import { test as base } from "@playwright/test";

// Every test starts as a returning visitor, so the first-visit autoplay does not race the test's own clicks.
// intro.spec.ts imports @playwright/test directly to test the first visit itself.
// status.json is answered "paused": these specs test the replay experience, which must not depend on whether the
// deployed backend happens to be live. Tests that need live register their own status.json route, which wins
// (Playwright runs the most recently registered matching route first). smoke.spec.ts checks the real file.
export const PAUSED = '{"live": false, "since": "test", "note": "paused"}';
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => localStorage.setItem("cg.visited", "1"));
    await page.route("**/status.json", (r) => r.fulfill({ contentType: "application/json", body: PAUSED }));
    await use(page);
  },
});

export { expect, type Page, type Route } from "@playwright/test";
