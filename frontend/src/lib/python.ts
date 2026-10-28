// Listing helpers for the model's output: strip the ``` fence, a small Python tokenizer for highlighting (works on
// incomplete code mid-stream: an unterminated string just runs to the end), and a naive unused-import note.

export type Tok = { k: "kw" | "def" | "str" | "doc" | "com" | "num" | "dec" | "bi" | "txt"; v: string };

const KW = new Set(
  "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case".split(" "),
);
const BI = new Set("int float str bool list dict set tuple bytes object len range print isinstance enumerate zip min max sum sorted abs any all map filter type super".split(" "));

/** The code inside the first ```python fence; mid-stream, everything after the opening fence. */
export function extractCode(text: string): string {
  const open = text.match(/```[a-zA-Z0-9_+-]*\n?/);
  if (!open || open.index === undefined) return text;
  const rest = text.slice(open.index + open[0].length);
  const close = rest.indexOf("```");
  return (close >= 0 ? rest.slice(0, close) : rest).replace(/\n$/, "");
}

export function tokenize(src: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  let prevWord = "";
  const push = (k: Tok["k"], v: string) => {
    const last = out[out.length - 1];
    if (last && last.k === k && k === "txt") last.v += v;
    else out.push({ k, v });
  };
  while (i < src.length) {
    const c = src[i];
    const rest = src.slice(i);
    if (c === "#") {
      const end = src.indexOf("\n", i);
      const j = end < 0 ? src.length : end;
      push("com", src.slice(i, j));
      i = j;
      continue;
    }
    const sm = rest.match(/^([rRbBuUfF]{0,2})("""|'''|"|')/);
    if (sm) {
      const q = sm[2];
      let j = i + sm[0].length;
      for (;;) {
        if (j >= src.length) break;
        if (src[j] === "\\") { j += 2; continue; }
        if (src.startsWith(q, j)) { j += q.length; break; }
        if (q.length === 1 && src[j] === "\n") break;
        j++;
      }
      const v = src.slice(i, Math.min(j, src.length));
      // A triple-quoted string that starts a line is a docstring.
      const lineStart = src.lastIndexOf("\n", i - 1) + 1;
      push(q.length === 3 && /^\s*$/.test(src.slice(lineStart, i)) ? "doc" : "str", v);
      i += v.length;
      continue;
    }
    const nm = rest.match(/^\d[\d_]*(\.\d+)?([eE][+-]?\d+)?/);
    if (nm && !/\w/.test(src[i - 1] ?? "")) {
      push("num", nm[0]);
      i += nm[0].length;
      continue;
    }
    if (c === "@" && /^\s*$/.test(src.slice(src.lastIndexOf("\n", i - 1) + 1, i))) {
      const m = rest.match(/^@[\w.]+/);
      if (m) { push("dec", m[0]); i += m[0].length; continue; }
    }
    const wm = rest.match(/^[A-Za-z_]\w*/);
    if (wm) {
      const w = wm[0];
      if (prevWord === "def" || prevWord === "class") push("def", w);
      else if (KW.has(w)) push("kw", w);
      else if (BI.has(w)) push("bi", w);
      else push("txt", w);
      prevWord = w;
      i += w.length;
      continue;
    }
    if (!/\s/.test(c)) prevWord = "";
    push("txt", c);
    i++;
  }
  return out;
}

export type Note = { line: number; text: string };

/** Imported names never used again. Naive (text search, ignores scope and __all__); labelled as such in the UI. */
export function unusedImports(code: string): Note[] {
  const lines = code.split("\n");
  const notes: Note[] = [];
  lines.forEach((ln, idx) => {
    const m = ln.match(/^\s*from\s+[\w.]+\s+import\s+(.+)$/) ?? ln.match(/^\s*import\s+(.+)$/);
    if (!m) return;
    const names = m[1].replace(/[()]/g, "").split(",").map((s) => s.trim()).filter(Boolean)
      .map((s) => (s.includes(" as ") ? s.split(" as ")[1] : s.split(".")[0]).trim());
    const body = lines.filter((_, j) => j !== idx).join("\n");
    for (const n of names) {
      if (n !== "*" && !new RegExp(`\\b${n.replace(/[^\w]/g, "")}\\b`).test(body)) notes.push({ line: idx + 1, text: `unused import ${n}` });
    }
  });
  return notes;
}

/** fibonacci.py from the first def/class, else generated.py. */
export function suggestFilename(code: string): string {
  const m = code.match(/^\s*(?:def|class)\s+([A-Za-z_]\w*)/m);
  return `${m ? m[1].replace(/([a-z])([A-Z])/g, "$1_$2").toLowerCase() : "generated"}.py`;
}
