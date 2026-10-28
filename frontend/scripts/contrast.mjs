// WCAG 2.2 contrast audit of every theme preset in src/styles/globals.css. Exit 1 on any failure.
//   node scripts/contrast.mjs
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles/globals.css", import.meta.url), "utf8");
const themes = {};
for (const m of css.matchAll(/\[data-theme="(\w+)"\]\s*\{([^}]*)\}/g)) {
  themes[m[1]] = Object.fromEntries([...m[2].matchAll(/--(\w+):\s*(#[0-9a-f]{6})/gi)].map((x) => [x[1], x[2]]));
}
const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

// [foreground, backgrounds, minimum, why]
const TEXT = 4.5, UI = 3;
const checks = [
  ...["ink", "dim", "cu", "au", "tp", "sig2"].map((f) => [f, ["bg", "bg2", "act"], TEXT, "text"]),
  ["on", ["cu", "au", "tp"], TEXT, "button label on filled button (rest/hover/stop)"],
  ["gut", ["bg2"], TEXT, "line numbers (aria-hidden, but visible text)"],
  ["frame", ["bg"], UI, "panel frames"],
  ["au", ["bg", "bg2", "act"], UI, "focus ring"],
  ["ctl", ["bg", "bg2", "act"], UI, "control borders (textarea, chips, toggles, buttons)"],
];
let fails = 0;
for (const [name, t] of Object.entries(themes)) {
  const rows = [];
  for (const [fg, bgs, min, why] of checks)
    for (const bg of bgs) {
      const r = ratio(t[fg], t[bg]);
      if (r < min) fails++;
      rows.push({ pair: `${fg} on ${bg}`, ratio: r.toFixed(2), min, ok: r >= min ? "✓" : "FAIL", why });
    }
  console.log(`\n== ${name}`);
  console.table(rows.filter((r) => r.ok === "FAIL" || process.argv.includes("--all")));
}
console.log(fails ? `\n${fails} failing pairs` : "\nall pairs pass");
process.exit(fails ? 1 : 0);
