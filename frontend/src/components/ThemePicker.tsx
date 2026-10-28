import { useCallback, useEffect, useRef, useState } from "react";
import { THEMES, ThemeId, applyTheme, currentTheme, nextTheme } from "@/lib/themes";

export function Swatch({ colors }: { colors: string[] }) {
  return (
    <span className="swatch" aria-hidden="true">
      {colors.map((c) => (
        <span key={c} style={{ background: c }} />
      ))}
    </span>
  );
}

const typing = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.isContentEditable);

/** VS Code-style preset picker: button + radio menu. Shift+T cycles anywhere (except while typing); 1-4 pick in the menu. */
export function ThemePicker() {
  const [theme, setTheme] = useState<ThemeId>("soldermask");
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => setTheme(currentTheme()), []);

  const choose = useCallback((id: ThemeId, close = true) => {
    applyTheme(id);
    setTheme(id);
    if (close) {
      setOpen(false);
      btn.current?.focus();
    }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "T" && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !typing(e.target)) {
        e.preventDefault();
        choose(nextTheme(currentTheme()), false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choose]);

  useEffect(() => {
    if (!open) return;
    const items = () => Array.from(menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitemradio]") ?? []);
    items().find((b) => b.getAttribute("aria-checked") === "true")?.focus();
    const onKey = (e: KeyboardEvent) => {
      const list = items();
      const i = list.indexOf(document.activeElement as HTMLButtonElement);
      if (e.key === "Escape") { setOpen(false); btn.current?.focus(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); list[(i + 1) % list.length]?.focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); list[(i - 1 + list.length) % list.length]?.focus(); }
      else if (/^[1-4]$/.test(e.key)) { e.preventDefault(); choose(THEMES[Number(e.key) - 1].id); }
      else if (e.key === "Tab") setOpen(false);
    };
    const onDown = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open, choose]);

  const cur = THEMES.find((t) => t.id === theme)!;
  return (
    <div className="theme-wrap">
      <button ref={btn} type="button" className="theme-btn silk" aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} title="Theme (Shift+T cycles)" aria-label={`Theme: ${cur.label}`}>
        <Swatch colors={cur.swatch} />
        {/* all names share one grid cell: the box is always as wide as the longest, so the bar never reflows */}
        <span className="theme-name" aria-hidden="true">
          {THEMES.map((t) => <span key={t.id} className={t.id === theme ? "" : "ghost"}>{t.label}</span>)}
        </span>
        <span className="dim" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div ref={menu} className="theme-menu" role="menu" aria-label="Theme">
          <div className="head silk">Theme · saved in this browser</div>
          <ul>
            {THEMES.map((t, i) => (
              <li key={t.id} role="none">
                <button type="button" role="menuitemradio" aria-checked={t.id === theme} onClick={() => choose(t.id)}>
                  <span className="dot" aria-hidden="true">{t.id === theme ? "●" : ""}</span>
                  <Swatch colors={t.swatch} />
                  <span className="lbl">{t.label}<small>{t.hint}</small></span>
                  <kbd aria-hidden="true">{i + 1}</kbd>
                </button>
              </li>
            ))}
          </ul>
          <div className="foot"><kbd>Shift</kbd>+<kbd>T</kbd> cycles from anywhere · <kbd>1</kbd>–<kbd>4</kbd> select · <kbd>Esc</kbd> closes</div>
        </div>
      )}
    </div>
  );
}
