import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const THEMES = ["soldermask", "instrument", "tty", "datasheet"];

async function setTheme(page: Page, id: string) {
  await page.addInitScript((t) => localStorage.setItem("cg.theme", t), id);
}

for (const theme of THEMES) {
  for (const path of ["/", "/notes/"]) {
    test(`axe: no WCAG A/AA violations on ${path} in ${theme}`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "theme x page matrix runs once");
      await setTheme(page, theme);
      await page.goto(path);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      if (path === "/") {
        // audit a finished run too: highlighted code, readouts, run log
        await page.getByRole("button", { name: "Replay ▸" }).click();
        await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
      }
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      expect(r.violations.map((v) => `${v.id}: ${v.nodes.length} × ${v.nodes[0]?.target}`)).toEqual([]);
    });
  }
}

// status.json says paused -> the page settles in replay mode; keyboard tests start from there
async function settled(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay", exact: true })).toHaveAttribute("aria-pressed", "true");
}

async function focused(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const cs = getComputedStyle(el);
    return { text: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40), tag: el.tagName,
             ring: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 };
  });
}

test("keyboard: skip link, every stop has a visible focus ring, replay runs without a mouse", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await settled(page);
  await page.keyboard.press("Tab");
  expect((await focused(page)).text).toBe("Skip to controls");
  await page.keyboard.press("Enter");
  const stops: string[] = [];
  for (let i = 0; i < 30; i++) {  // walk every stop after the skip target until focus leaves the page
    await page.keyboard.press("Tab");
    const f = await focused(page);
    if (f.tag === "BODY") break;
    expect(f.ring, `focus ring on ${f.tag} "${f.text}"`).toBe(true);
    stops.push(f.text);
  }
  expect(stops.length).toBeGreaterThanOrEqual(8);
  expect(stops[0]).toBe("Replay"); // "Live" is disabled while paused, so it is skipped
  expect(stops).toContain("fibonacci");
  expect(stops).toContain("Replay ▸");
  // run the selected replay from the keyboard
  await page.getByRole("button", { name: "Replay ▸" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("clean EOS")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Copy" }).focus();
  expect((await focused(page)).ring).toBe(true);
});

test("keyboard: theme menu opens, arrows move, Enter selects, Escape returns focus", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await settled(page);
  const btn = page.getByRole("button", { name: /Theme · / });
  await btn.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitemradio", { name: /Soldermask/ })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitemradio", { name: /Instrument/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "instrument");
  await expect(btn).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("4");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "datasheet");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(btn).toBeFocused();
});

test("keyboard: Shift+T does not fire while typing", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await settled(page);
  await page.getByLabel("Recorded prompt").focus();
  await page.keyboard.press("Shift+T");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "soldermask");
});

test("reduced motion: no running animations", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Replay ▸" }).click();
  await expect(page.getByLabel("Generated code")).toBeVisible({ timeout: 10_000 });
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length);
  expect(running).toBe(0);
});
