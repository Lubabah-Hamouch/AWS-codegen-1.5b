// Copies the Pyodide runtime into public/pyodide/ so it is served from this site (CSP script-src 'self').
// Runs before dev and build (package.json pre-scripts). The copy is gitignored; the version is pinned in package.json.
import { copyFileSync, mkdirSync } from "node:fs";

const FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];
const src = new URL("../node_modules/pyodide/", import.meta.url);
const dst = new URL("../public/pyodide/", import.meta.url);
mkdirSync(dst, { recursive: true });
for (const f of FILES) copyFileSync(new URL(f, src), new URL(f, dst));
console.log(`pyodide runtime -> public/pyodide/ (${FILES.length} files)`);
