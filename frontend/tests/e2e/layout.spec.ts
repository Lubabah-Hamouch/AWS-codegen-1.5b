import { expect, test } from "@playwright/test";
// every preset, several widths: the theme button stays on the nav row, one line, same width
test("theme button: one line, on the nav row, nothing clipped, for every preset and width", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  for (const theme of ["soldermask", "instrument", "tty", "datasheet"]) {
    await page.addInitScript((t) => localStorage.setItem("cg.theme", t), theme);
    for (const w of [360, 700, 1000, 1440]) {
      await page.setViewportSize({ width: w, height: 600 });
      await page.goto("/");
      const btn = await page.locator(".theme-btn").boundingBox();
      const nav = await page.locator(".mast-nav").boundingBox();
      console.log(theme, w, Math.round(btn!.width), btn!.height, Math.round(btn!.y - nav!.y));
      expect(btn!.height).toBe(44);
      expect(Math.abs(btn!.y - nav!.y)).toBeLessThan(2);
      // nothing clipped: nav links and the name render at full width
      const clipped = await page.evaluate(() => [...document.querySelectorAll(".mast-nav a, .theme-name")].filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent));
      expect(clipped).toEqual([]);
      if (theme === "soldermask") await page.locator(".mast-bar").screenshot({ path: `test-results/bar-${w}.png` });
    }
  }
});
