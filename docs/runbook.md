# Runbook

Site: **https://d2js86b0xg0ozs.cloudfront.net** (playground and `/notes/`). Backend: Lambda `codegen-backend`.

## Going live to show someone (quick reference)

The service is **parked by default**: kill switch ON, site in replay mode. Turn it on deliberately, turn it off after.
There is no schedule that turns it on.

```powershell
infra\scripts\killswitch.ps1 off                    # 1. flag OFF, status.json -> live, URL auth -> NONE
curl.exe -m 150 https://sug6pvql5qkkk3tm7udviuyoc40jwvys.lambda-url.eu-north-1.on.aws/health   # 2. warm-up
#                                                      3. reload the site: U1 shows "Live", Run is enabled
infra\scripts\killswitch.ps1 on                     # 4. afterwards: both layers back on, status.json -> paused
```

- **Step 2 is not optional.** If the function is cold, the first visitor waits 4-9 s for the first token. `{"ready": true}`
  means warm. It works while the kill switch is ON, so it can come first.
- **Reload pages that were already open.** The site reads status.json once on load; an open tab stays in replay mode.
- **After `killswitch.ps1 on`, the next `off` takes ~25-40 s to take effect** (the URL auth change propagates slowly; requests
  can flap 200/403 meanwhile). If you will switch again soon, park with `python infra\scripts\seed_state.py --kill on`
  instead: layer 1 only, takes effect immediately in both directions, still refuses every generation.
- **Several people on one network share one IP**, so 5 live runs/day between them. For a demo:
  `python infra\scripts\seed_state.py --set anon_ip_daily=20`, and back to `anon_ip_daily=5` afterwards. The global cap
  (100/day) keeps the month inside the free tier either way.
- Check state any time: `infra\scripts\killswitch.ps1 status` (URL auth type, kill flag, limits).
- If the page says "Paused by circuit breaker", the breaker tripped on an invocation flood. Find out why (CloudWatch
  `Invocations` for `codegen-backend`) before turning it back on.

Account `<ACCOUNT_ID>`, region **eu-north-1** (Stockholm). Profile `codegen-spike`. The account is a "project account"
in AWS's new sign-up experience: AWS manages its Organization SCPs, and everything outside the project region is denied.

## Emergency stop (read this first)

| Layer | How | Speed |
|---|---|---|
| **1. App kill switch** | `python infra/scripts/seed_state.py --kill on` (DynamoDB flag `config#killswitch`) | **Immediate.** The next request gets 503 and no model work is done. |
| **2. Function URL auth switch** | `infra/scripts/killswitch.ps1 on` (flips the URL to `AWS_IAM`; AWS answers 403 before any code runs) | **NOT instant. Measured 35-41 s before it took effect, ~25 s to reverse, and the status flaps (200/403/429) in between.** Occasionally ~3 s. Do not assume it has taken effect: poll `GET <url>/health` until it returns 403 twice in a row. |
| **Automatic: circuit breaker** | CloudWatch alarm `codegen-backend-invocation-flood` (> 600 invocations in 5 min) -> SNS -> `codegen-breaker` Lambda engages layers 1 and 2 | Alarm needs one 5-minute period plus metric delay (a few minutes), then layer 2's propagation. |

- Layer 1 is the real stop for *work*. Only layer 2 stops *invocations*, and every request that reaches the URL is a billed
  invocation even when the app refuses it. That is why the circuit breaker exists: in-app limits cannot cap the cost of a
  flood, so the breaker turns the URL off when invocations spike.
- `killswitch.ps1` defaults to `codegen-backend`.
- `killswitch.ps1 on` engages both layers. A later `sam deploy` resets layer 2 to the template (`AuthType: NONE`).
- Both layers cut off traffic but do not stop an invocation already running; the longest is the 90 s function timeout.
- After the breaker trips, recovery is manual: find the cause, then `killswitch.ps1 off`.
- The deployed state is parked with layer 1 **ON** unless someone has deliberately turned it off.

Lambda reserved concurrency is not available (account quota is 10; AWS needs 100 unreserved). A quota increase
request is pending (`d11cd98e7fb74f548ee977967d8d0df6C7iTHQM7`, to 1100). Until it is approved the concurrency cap is the
application's slot lock (`backend/app/guard.py`, `max_concurrency` in `config#global`). The account limit of 10
concurrent executions also bounds how fast a flood can run.

## Guardrail state (DynamoDB table `codegen-state`)

| Item | Meaning |
|---|---|
| `config#killswitch` `{enabled, reason}` | layer 1 (`reason` says "circuit breaker ..." if the breaker set it) |
| `config#global` | `global_daily`, `max_concurrency`, `slot_seconds`, `max_tokens`, `anon_total_daily`, `anon_ip_daily` |
| `key#<sha256>` `{name, daily_limit, enabled}` | hand-made API keys (only the hash is stored) |
| `day#<date>#...` | daily counters (TTL 3 days) |
| `slot#0..N-1` | concurrency leases; they expire on their own |

Change limits with `python infra/scripts/seed_state.py --set global_daily=100 anon_ip_daily=5 ...`; `--show` prints them.
The demo key is in `infra/.demo-key` (gitignored). Any error reading this table makes the app refuse the request (fail closed).

Anonymous per-IP limits key on the Function URL's own `requestContext.http.sourceIp` (forwarded by the Web Adapter in
`x-amzn-request-context`). `x-forwarded-for` is **not** used: the Function URL passes a client-supplied one through
unchanged, so it was forgeable (measured).

## Deploy the backend

```powershell
infra\scripts\build_push.ps1 -Dockerfile Dockerfile -Tag model-N          # arm64 image -> ECR (prints IMAGE_URI)
cd infra
sam deploy -t backend.yaml --stack-name codegen-backend `
  --image-repository <ACCOUNT_ID>.dkr.ecr.eu-north-1.amazonaws.com/codegen-backend `
  --parameter-overrides "ImageUri=<IMAGE_URI> SiteOrigin=https://d2js86b0xg0ozs.cloudfront.net StatusBucket=codegen-frontend-sitebucket-xwl33y2kvcnw"
curl.exe -m 150 <FunctionUrl>/health                                       # WARM-UP after every new image
python infra\scripts\live_tests_model.py <FunctionUrl>                     # kill switch, caps, keys, SSE, out-of-band kill
python infra\scripts\live_tests_hardening.py <FunctionUrl>                 # IP spoofing, daily warm-up, circuit breaker
```

- **Warm-up after every new image.** If the **model layer** is new to Lambda (first deploy, or a new GGUF), the first start
  takes ~75-90 s: Lambda fetches the 1 GB layer, init exceeds 10 s and is retried inside the invocation, right at the 90 s
  timeout. If only the app layer changed, the first start took 11 s. Later cold starts take 4-9 s. `/health` is unguarded,
  so the warm-up works while the kill switch is ON. Repeat it if the first call times out.
- `SiteOrigin` is the only browser origin CORS allows (plus `http://localhost:3000` for `npm run dev`); `StatusBucket` is
  where the breaker writes status.json. Both are outputs of the `codegen-frontend` stack.
- `--image-repository` is required by SAM for image functions; pointing it at our repo stops SAM creating a companion repo.
- **Memory is capped at 3008 MB on this account.** 3008 MB / 2 threads is the chosen config; see
  [backend_capacity.md](backend_capacity.md) for the measurements and the free-tier math.
- The first image push uploads the ~1 GB model layer (took 33 min on this connection). Later pushes reuse it (seconds).
- Benchmarks change the function's memory and environment directly; restore the template values afterwards
  (3008 MB, `LLAMA_THREADS=2`, no `LLAMA_EXTRA`) or redeploy.

Stacks: `codegen-persistent` (DynamoDB, retained), `codegen-ecr` (image repo, keeps the newest 2), `codegen-backend`
(function, URL, daily warm-up rule, alarm, SNS topic, breaker), `codegen-frontend` (site bucket, CloudFront). Tear down with
`infra\teardown.ps1` (backend only) or `-All` (everything; empties the site bucket first, keeps the retained table).

Function URL: `https://sug6pvql5qkkk3tm7udviuyoc40jwvys.lambda-url.eu-north-1.on.aws/` (POST `/generate`, GET `/health`).

## status.json (how the site knows the backend is paused)

`https://<site>/status.json` = `{"live": bool, "since": "<UTC>", "note": "live" | "paused" | "circuit breaker"}`.

- Written to the site bucket by `seed_state.py --kill on|off` (so also by `killswitch.ps1`) and by the circuit breaker.
  `python infra\scripts\seed_state.py --status` re-publishes it from the current kill flag if it ever drifts.
- Served by CloudFront with caching disabled, and stored with `Cache-Control: no-store`. Reading it costs no Lambda invocation,
  which is the point: a parked backend shows replays without anyone sending requests that would fail.
- The site reads it once on page load. `live: false` -> replay mode and the "paused" banner. Missing or unreadable -> the
  site assumes live and lets the first request decide.
- It is advisory. The guardrails are what actually refuse requests; a stale `live: true` only means a visitor sees a
  coded refusal (`disabled`) and the page switches itself to replay mode.
- The frontend deploy never overwrites it (excluded from the sync).

## Deploy the frontend

```powershell
frontend\scripts\deploy.ps1 -From frontend-out-<sha>.zip -DryRun   # what would change (lists only)
frontend\scripts\deploy.ps1 -From frontend-out-<sha>.zip           # s3 sync -> CloudFront invalidation
```

Then run the **smoke** workflow (GitHub Actions tab -> smoke -> Run workflow): smoke, layout, a11y and test bench specs
against the deployed site, from a clean browser. `cd frontend; npx playwright test` runs the same locally.

- The zip is the `frontend-out-<sha>` artifact of a green `ci` run (run page -> Artifacts). It is the build that passed
  the tests; `build-info.txt` inside names the commit, and `deploy.ps1` prints it and never uploads it.
- `deploy.ps1` with no `-From` builds locally first (the old flow); both paths run the CSP check before uploading.
- Deploys are manual on purpose. CI has no AWS access: this account's organization SCP denies the IAM OIDC provider
  APIs, so GitHub Actions cannot get short-lived credentials, and stored access keys are not an option.

- Stack `codegen-frontend` (`infra/frontend.yaml`): private S3 bucket, CloudFront with origin access control, a viewer-request
  function mapping `/notes/` to `/notes/index.html`, security headers. CSP: `script-src 'self'`, `connect-src` = the Function URL.
- **Webpack, not Turbopack.** Turbopack's static export injects an inline `<script>`, which that CSP blocks.
  `scripts/check-csp.mjs` fails CI and `deploy.ps1` refuses to publish if any inline script appears in the export.
- `_next/` assets are cached for a year (hashed names); HTML and replays for 60 s, and each deploy invalidates `/*`.
- The API URL is in `frontend/.env.production` / `.env.development` (public by design). The demo API key is never used by
  the frontend.
- Checks: `npm test` (25 unit), `node scripts/contrast.mjs` (WCAG contrast of all four themes),
  `LIVE=1 npx playwright test tests/e2e/live.spec.ts` (one real cross-origin run; kill switch must be OFF).
- Local dev: `cd frontend; npm run dev` -> http://localhost:3000 (no status.json locally, so it starts in live mode).
- Local check of the real build under the real CSP: `npm run build`, then `python scripts/serve_static.py` (serves `out/`
  like CloudFront: same CSP and headers, a parked status.json) and `BASE_URL=http://127.0.0.1:3999 npx playwright test
  --workers=1`. One worker: the single-process server cannot feed several browsers downloading the Python runtime at once.

## Test bench (U6: running the generated code)

- Runs entirely in the visitor's browser: Pyodide (CPython on WebAssembly, pinned in `frontend/package.json`) in a Web
  Worker created per run and terminated afterwards (`public/testbench.worker.mjs`, `src/lib/testbench.ts`). No backend,
  no AWS cost, no change to the backend's risk profile.
- Loaded on demand only: nothing under `/pyodide/` is requested until someone presses Run checks / Run code (a test
  asserts this). The runtime (~13.5 MB on disk, ~6 MB over the wire with CloudFront compression) is copied from `node_modules/pyodide` into `public/pyodide/` before every dev/build
  (`scripts/copy-pyodide.mjs`; the copy is gitignored).
- Limits: 5 s per run (then the worker is terminated), 90 s to boot on first use. Network from inside it is whatever the
  CSP allows (the site and the Function URL).
- CSP: the only addition is `'wasm-unsafe-eval'` in `script-src` (WebAssembly compilation; JS `eval` stays blocked).
- `deploy.ps1` uploads `.mjs` as `text/javascript` and `.wasm` as `application/wasm` explicitly: the site sends `nosniff`,
  so a wrong type would stop the worker from loading.
- Checks: hand-written suites for the five example prompts, exact text only, in `src/data/checks.ts`. Anything else
  (custom or edited prompt, stopped run) gets a behavioural report, never pass/fail. Keep suites in step with
  `EXAMPLES` in `src/data/facts.ts`; a unit test fails if the counts differ.
- After re-recording replays, check them against the suites and update the "recorded replay" column in the /notes Test
  bench table (it states the current results, including the merge_intervals failure).

## Record new replays

Needed after anything that changes outputs (new model, new prompt version) so replays match what the live backend produces.

```powershell
python frontend\scripts\record_replays.py            # kill OFF -> warm-up -> 5 runs -> kill ON (always, via atexit)
frontend\scripts\deploy.ps1
```

- Prompts are the list in the script (`RUNS`), kept in step with the example chips in `frontend/src/data/facts.ts`.
- Each run uses the demo key (`infra/.demo-key`, 20/day), so recording does not spend the anonymous quota; the key and the
  quota left are not written to the files. Output: `frontend/public/replays/<id>.json` + `index.json`.
- A recording stores every token with its arrival time (ms since the request was sent), the first-byte time, and the
  server's `done` event. The site replays that timing exactly and labels it "Replay" with the recording time and host.

## Scheduled warm-up

EventBridge rule (`rate(1 day)`) invokes the function directly with `{"source": "codegen.daily-warmup"}`; the Web Adapter
delivers it as `POST /events`, which returns 200. It is insurance against the image cache going cold during long idle
periods (AWS does not document whether that happens). Cost: about one cold start a day, ~11 GB-s, ~340 GB-s/month.
It bypasses both kill-switch layers (direct invoke, not the URL), which is intended; it does no model generation.

## Tests

CI (`.github/workflows/ci.yml`) runs on every push and pull request, with no AWS access:

- `frontend`: `npm ci`, typecheck, unit tests, contrast check, build, CSP check; uploads the export as `frontend-out-<sha>`
  (kept 30 days).
- `backend-guard`: the guard tests against a pinned DynamoDB Local service. `REQUIRE_DDB=1` turns "unreachable" into a
  failure instead of a skip.
- `training-cpu`: `training/tests` without `test_sft_labels.py` (needs torch and the real tokenizer; run it in the training
  environment).

Not in CI: GPU training, real-model evals, the Lambda image and stacks, and the live suites below.

- `python -m pytest backend/tests` with DynamoDB Local on :8000: guard logic (11 tests).
- `python backend/tests/e2e_local.py <image>`: the real app, real model, DynamoDB Local (17 checks).
- `infra/scripts/live_tests_model.py`: the guardrails against the deployed function.
- `infra/scripts/live_tests_hardening.py`: client-IP spoofing, the warm-up rule and event, the circuit breaker end to end
  (it drives the real alarm into ALARM with `set-alarm-state`).

- `frontend`: `npm test`, `npx playwright test`, `node scripts/contrast.mjs` (see "Deploy the frontend").

## Known limits

- `/health` and `/events` are unguarded (the Web Adapter and the schedule need them). Each call is a ~3 ms invocation;
  a flood of them is what the circuit breaker is for.
- Function URL changes made out of band propagate slowly (see above).
- Not yet verified: whether a function idle for days or weeks pays the ~75 s model-layer fetch again on its next cold start.
  The daily warm-up's REPORT lines in CloudWatch will show it if it happens.
