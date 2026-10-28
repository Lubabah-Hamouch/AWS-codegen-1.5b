// Fails if the static export contains an inline <script>, which the site's CSP (script-src 'self') would block.
// JSON data islands (type application/json) are not executed and are allowed.
// Used by CI after the build and by deploy.ps1 before publishing.   node scripts/check-csp.mjs [dir]
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = process.argv[2] ?? fileURLToPath(new URL("../out", import.meta.url));
const INLINE = /<script(?![^>]*src=)(?![^>]*application\/json)[^>]*>/g;
const html = readdirSync(dir, { recursive: true }).filter((f) => f.endsWith(".html"));
if (!html.length) {
  console.error(`no .html files under ${dir}`);
  process.exit(1);
}
const hits = html.flatMap((f) => (readFileSync(join(dir, f), "utf8").match(INLINE) ?? []).map((m) => `${f}: ${m}`));
for (const h of hits) console.error(`inline <script> would be blocked by the CSP: ${h}`);
console.log(`${html.length} html files, ${hits.length} inline scripts`);
process.exit(hits.length ? 1 : 0);
