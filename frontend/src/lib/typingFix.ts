// Generation-time mitigation for one mechanical defect: typing names used in type hints but never imported (the shipped
// model writes `-> Tuple[int, int]` with only `from typing import List`; the function then fails with NameError). The
// browser adds the missing names before the code is shown, copied, saved or run, and the listing marks the line.
// Twin of training/data_pipeline/typing_fix.py; both reproduce training/data_pipeline/typing_fix_cases.json.

export const TYPING_NAMES = new Set([
  "Any", "AnyStr", "AsyncGenerator", "AsyncIterable", "AsyncIterator", "Awaitable", "Callable", "ChainMap",
  "ClassVar", "Collection", "Container", "ContextManager", "Coroutine", "Counter", "DefaultDict", "Deque", "Dict",
  "Final", "FrozenSet", "Generator", "Generic", "Hashable", "IO", "ItemsView", "Iterable", "Iterator", "KeysView",
  "List", "Literal", "Mapping", "MappingView", "Match", "MutableMapping", "MutableSequence", "MutableSet",
  "NamedTuple", "NoReturn", "Optional", "OrderedDict", "Pattern", "Protocol", "Reversible", "Sequence", "Set",
  "Sized", "SupportsFloat", "SupportsIndex", "SupportsInt", "Text", "TextIO", "Tuple", "Type", "TypeVar",
  "TypedDict", "Union", "ValuesView",
]);

export type TypingFix = { code: string; added: string[]; line: number | null }; // line: 1-based, the import line

const KEYWORDS = /^(if|elif|else|for|while|with|try|except|finally|def|class|lambda|return|match|case|async|await|assert|del|global|nonlocal|pass|raise|yield|import|from)\b/;
const OPEN = "([{";
const CLOSE = ")]}";

/** Comments and string contents blanked to spaces (offsets kept), plus where each string's contents are. */
function mask(src: string): { masked: string; strings: [number, number][] } {
  const out = src.split("");
  const strings: [number, number][] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "#") {
      while (i < src.length && src[i] !== "\n") out[i++] = " ";
    } else if (c === "'" || c === '"') {
      const q = src.startsWith(c.repeat(3), i) ? c.repeat(3) : c;
      const start = i + q.length;
      let j = start;
      while (j < src.length && !src.startsWith(q, j) && !(q.length === 1 && src[j] === "\n")) j += src[j] === "\\" ? 2 : 1;
      for (let k = start; k < Math.min(j, src.length); k++) if (src[k] !== "\n") out[k] = " ";
      strings.push([start, Math.min(j, src.length)]);
      i = j + q.length;
    } else i++;
  }
  return { masked: out.join(""), strings };
}

/** Identifiers an annotation needs, top-level names only (`typing.List` -> typing), including inside quoted hints. */
function names(src: string, m: string, strings: [number, number][], from: number, to: number, acc: Set<string>) {
  const scan = (text: string) => {
    for (const x of text.matchAll(/(\.\s*)?\b([A-Za-z_]\w*)/g)) if (!x[1]) acc.add(x[2]);
  };
  scan(m.slice(from, to));
  for (const [s, e] of strings) if (s >= from && e <= to) scan(src.slice(s, e));
}

/** End of an expression starting at i: the first depth-0 character in `stops`. */
function until(m: string, i: number, stops: string): number {
  let depth = 0;
  for (; i < m.length; i++) {
    const c = m[i];
    if (OPEN.includes(c)) depth++;
    else if (CLOSE.includes(c)) {
      if (depth === 0) return i;
      depth--;
    } else if (depth === 0 && stops.includes(c)) {
      if (c === "=" && (m[i + 1] === "=" || "<>!".includes(m[i - 1]))) continue;
      if (c === "-" && m[i + 1] !== ">") continue;
      return i;
    } else if (depth === 0 && c === "\n" && stops.includes("\n")) return i;
  }
  return m.length;
}

function hintNames(src: string): { used: Set<string>; known: Set<string>; star: boolean } {
  const { masked: m, strings } = mask(src);
  const used = new Set<string>();
  const known = new Set<string>();
  let star = false;
  // function signatures: parameter annotations and the return annotation
  for (const d of m.matchAll(/(^|\n)[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)[ \t]*\(/g)) {
    known.add(d[2]);
    const open = d.index! + d[0].length;
    const close = until(m, open, "");
    let p = open;
    while (p < close) {
      const end = Math.min(until(m, p, ","), close);
      const colon = until(m, p, ":=,");
      if (colon < end && m[colon] === ":") names(src, m, strings, colon + 1, Math.min(until(m, colon + 1, "=,"), end), used);
      p = end + 1;
    }
    let r = close + 1;
    while (r < m.length && " \t\\\n".includes(m[r])) r++;
    if (m.startsWith("->", r)) names(src, m, strings, r + 2, until(m, r + 2, ":"), used);
  }
  // logical lines at bracket depth 0: annotated assignments, imports, class names, simple assignments
  let depth = 0;
  let lineStart = 0;
  for (let i = 0; i <= m.length; i++) {
    const c = m[i];
    if (i === m.length || (c === "\n" && depth === 0)) {
      const raw = m.slice(lineStart, i);
      const line = raw.replace(/\\\n/g, " ");
      const ann = line.match(/^[ \t]*([A-Za-z_][\w.]*(?:\[[^\]\n]*\])?)[ \t]*:(?!=)/);
      if (ann && !KEYWORDS.test(line.trim())) {
        const from = lineStart + ann[0].length;
        names(src, m, strings, from, until(m, from, "=\n"), used);
        if (/^\w+$/.test(ann[1])) known.add(ann[1]);
      }
      const fi = line.match(/^[ \t]*from[ \t]+[\w.]+[ \t]+import[ \t]+([\s\S]*)$/);
      if (fi) {
        for (const part of fi[1].replace(/[()\\]/g, " ").split(",")) {
          const t = part.trim().split(/\s+as\s+/);
          if (t[0] === "*") star = true;
          else if (t[0]) known.add((t[1] ?? t[0]).trim());
        }
      }
      const im = line.match(/^[ \t]*import[ \t]+([\s\S]*)$/);
      if (im) for (const part of im[1].split(",")) {
        const t = part.trim().split(/\s+as\s+/);
        if (t[0]) known.add((t[1] ?? t[0].split(".")[0]).trim());
      }
      const cls = line.match(/^[ \t]*class[ \t]+([A-Za-z_]\w*)/);
      if (cls) known.add(cls[1]);
      const asg = line.match(/^[ \t]*([A-Za-z_]\w*)[ \t]*=(?!=)/);
      if (asg) known.add(asg[1]);
      lineStart = i + 1;
    } else if (c && OPEN.includes(c)) depth++;
    else if (c && CLOSE.includes(c)) depth = Math.max(0, depth - 1);
  }
  return { used, known, star };
}

/** Brackets balance outside strings and comments: the browser's stand-in for "the code parses" (the Python twin
 *  uses ast.parse; partial output from a stopped run is the usual unbalanced case). */
function balanced(src: string): boolean {
  const stack: string[] = [];
  for (const c of mask(src).masked) {
    if (OPEN.includes(c)) stack.push(c);
    else if (CLOSE.includes(c) && stack.pop() !== OPEN[CLOSE.indexOf(c)]) return false;
  }
  return stack.length === 0;
}

/** Add missing typing names to the code's `from typing import` line (or insert one). Nothing else changes, and code
 *  that does not look complete (unbalanced brackets) is left alone. */
export function fixTypingImports(code: string): TypingFix {
  if (!code.trim() || !balanced(code)) return { code, added: [], line: null };
  const { used, known, star } = hintNames(code);
  if (star) return { code, added: [], line: null };
  const added = [...used].filter((n) => TYPING_NAMES.has(n) && !known.has(n)).sort();
  if (!added.length) return { code, added, line: null };
  const lines = code.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^from[ \t]+typing[ \t]+import[ \t]+([A-Za-z_][\w \t,]*?)[ \t]*(#.*)?$/);
    if (m) {
      const have = m[1].split(",").map((s) => s.trim()).filter(Boolean);
      lines[i] = "from typing import " + [...have, ...added].join(", ") + (m[2] ? `  ${m[2]}` : "");
      return { code: lines.join("\n"), added, line: i + 1 };
    }
  }
  let at = 0;
  lines.forEach((ln, i) => { if (ln.startsWith("from __future__ import")) at = i + 1; });
  lines.splice(at, 0, "from typing import " + added.join(", "));
  return { code: lines.join("\n"), added, line: at + 1 };
}

/** The code the page shows, copies, saves and runs: the model's code block, with the import fix once it is complete. */
export function servedCode(code: string, finished: boolean): TypingFix {
  return finished ? fixTypingImports(code) : { code, added: [], line: null };
}
