// Named presets only. Colours live in globals.css under [data-theme=...]; the swatches here are for the picker.
// public/theme-init.js applies the saved choice before first paint and must list the same ids.

export type ThemeId = "soldermask" | "instrument" | "tty" | "datasheet";

export const THEMES: { id: ThemeId; label: string; hint: string; swatch: string[] }[] = [
  { id: "soldermask", label: "Soldermask", hint: "PCB green, copper traces", swatch: ["#0b241c", "#e8e4d8", "#d79a5b", "#e3c26b", "#ec8174"] },
  { id: "instrument", label: "Instrument", hint: "amber on black", swatch: ["#0d0c0a", "#f2e6cf", "#e8a33a", "#ffcf6b", "#ef7d6d"] },
  { id: "tty", label: "TTY", hint: "neutral terminal, ANSI accents", swatch: ["#121212", "#d0d0d0", "#5fd7af", "#ffd75f", "#ff5f87"] },
  { id: "datasheet", label: "Datasheet", hint: "light, printed-sheet contrast", swatch: ["#ffffff", "#111111", "#a3561a", "#7a5600", "#c8102e"] },
];

export const DEFAULT_THEME: ThemeId = "soldermask";
const KEY = "cg.theme";

export function currentTheme(): ThemeId {
  const t = typeof document !== "undefined" ? document.documentElement.getAttribute("data-theme") : null;
  return THEMES.some((x) => x.id === t) ? (t as ThemeId) : DEFAULT_THEME;
}

export function applyTheme(id: ThemeId) {
  document.documentElement.setAttribute("data-theme", id);
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* not persisted; still applied */
  }
}

export function nextTheme(id: ThemeId): ThemeId {
  const i = THEMES.findIndex((t) => t.id === id);
  return THEMES[(i + 1) % THEMES.length].id;
}
