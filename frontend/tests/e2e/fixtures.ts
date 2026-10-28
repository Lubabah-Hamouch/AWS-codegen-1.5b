import { test as base } from "@playwright/test";

// Every test starts as a returning visitor, so the first-visit autoplay does not race the test's own clicks.
// intro.spec.ts imports @playwright/test directly to test the first visit itself.
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => localStorage.setItem("cg.visited", "1"));
    await use(page);
  },
});

export { expect, type Page, type Route } from "@playwright/test";
