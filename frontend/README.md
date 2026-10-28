# frontend

The playground site: a static Next.js export (pages router, built with webpack) served from S3 behind CloudFront.

| Path | Contents |
|---|---|
| `src/pages/index.tsx` | The playground: prompt in, guard and model readouts, streamed listing, test bench |
| `src/pages/notes.tsx` | `/notes`, the datasheet: API, runtime, evaluation, cost, guardrails, training, limitations, test bench |
| `src/components/` | The panels (masthead, signal path, readouts, listing, test bench, side panels, theme picker) |
| `src/lib/` | SSE parser, API client and error mapping, run state machine, replay playback, status.json, themes, test bench runner |
| `src/data/facts.ts` | Every measured number shown on the site, with its source doc |
| `src/data/checks.ts` | Hand-written check suites for the five example prompts |
| `public/replays/` | Five recorded real runs, played back while the backend is paused |
| `public/testbench.worker.mjs` | Web Worker that runs generated code in Pyodide (CPython on WebAssembly) |
| `scripts/` | `deploy.ps1`, `copy-pyodide.mjs` (runs before dev/build), `check-csp.mjs` (no inline scripts in the export), `record_replays.py`, `contrast.mjs`, `serve_static.py` |

## Run

```bash
npm ci
npm run dev            # http://localhost:3000, talks to the real backend (CORS allows localhost:3000)
```

## Test

```bash
npm test               # unit tests (vitest)
npm run typecheck
node scripts/contrast.mjs   # WCAG contrast of all four themes
npx playwright test    # browser tests against the deployed site: replay, layout, keyboard, axe, test bench
```

`LIVE=1 npx playwright test tests/e2e/live.spec.ts` makes one real generation (the backend must be live). To test a
local build under the site's real CSP, see [docs/runbook.md](../docs/runbook.md#deploy-the-frontend), which also covers
deploying and re-recording replays.
