// Writes public/og.png (1200x630, the link-preview image) from the top of the home page: masthead and intro, default
// theme, nothing playing. Re-run after changing the intro, against a local build:
//   npm run build; python scripts/serve_static.py      then   node scripts/og-image.mjs [baseUrl]
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:3999";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
await page.addInitScript(() => localStorage.setItem("cg.visited", "1"));
await page.goto(`${base}/`);
await page.getByRole("button", { name: "Watch a recorded run ▸" }).waitFor();
await page.screenshot({ path: new URL("../public/og.png", import.meta.url).pathname.replace(/^\/(\w:)/, "$1") });
await browser.close();
console.log("public/og.png (1200x630)");
