# Backend runbook

Account `<redacted-account-id>`, region **eu-north-1** (Stockholm). Profile `codegen-spike`. The account is a "project account"
in AWS's new sign-up experience: AWS manages its Organization SCPs, and everything outside the project region is denied.

## Emergency stop (read this first)

| Layer | How | Speed |
|---|---|---|
| **1. App kill switch** | `python infra/scripts/seed_state.py --kill on` (DynamoDB flag `config#killswitch`) | **Immediate.** The next request gets 503 and no model work is done. |
| **2. Function URL auth switch** | `infra/scripts/killswitch.ps1 on` (flips the URL to `AWS_IAM`; AWS answers 403 before any code runs) | **NOT instant. Measured 35-41 s before it took effect, ~25 s to reverse, and the status flaps (200/403/429) in between.** Occasionally ~3 s. Do not assume it has taken effect: poll `GET <url>/health` until it returns 403 twice in a row. |

- Layer 1 is the real stop. Layer 2 is a backstop that still works if the app or the table is broken, but it needs up to a
  minute or more to propagate, in both directions. Plan for that delay when relying on it.
- `killswitch.ps1 on` engages both. A later `sam deploy` resets layer 2 to the template (`AuthType: NONE`).
- Both layers cut off traffic but do not stop an invocation already running; the longest is the 90 s function timeout.
- The deployed state is parked with layer 1 **ON** unless someone has deliberately turned it off.

Lambda reserved concurrency is not available (account quota is 10; AWS needs 100 unreserved). A quota increase
request is pending (`d11cd98e7fb74f548ee977967d8d0df6C7iTHQM7`, to 1100). Until it is approved the concurrency cap is the
application's slot lock (`backend/app/guard.py`, `max_concurrency` in `config#global`).

## Guardrail state (DynamoDB table `codegen-state`)

| Item | Meaning |
|---|---|
| `config#killswitch` `{enabled}` | layer 1 |
| `config#global` | `global_daily`, `max_concurrency`, `slot_seconds`, `max_tokens`, `anon_total_daily`, `anon_ip_daily` |
| `key#<sha256>` `{name, daily_limit, enabled}` | hand-made API keys (only the hash is stored) |
| `day#<date>#...` | daily counters (TTL 3 days) |
| `slot#0..N-1` | concurrency leases; they expire on their own |

Change limits with `python infra/scripts/seed_state.py --set global_daily=100 anon_ip_daily=5 ...`; `--show` prints them.
The demo key is in `infra/.demo-key` (gitignored). Any error reading this table makes the app refuse the request (fail closed).

## Deploy

```powershell
infra\scripts\build_push.ps1 -Dockerfile Dockerfile -Tag model-N          # arm64 image -> ECR (prints IMAGE_URI)
cd infra; sam deploy -t backend.yaml --stack-name codegen-backend --parameter-overrides "ImageUri=<IMAGE_URI>"
curl.exe -m 150 <FunctionUrl>/health                                       # WARM-UP: required after every new image
python infra\scripts\live_tests_model.py <FunctionUrl>                     # kill switch, caps, keys, SSE, out-of-band kill
```

- **Warm-up after every new image.** The first start of a newly deployed image takes ~75-90 s (Lambda fetches the 1 GB
  image; init exceeds 10 s and is retried inside the invocation, right at the 90 s timeout). Later cold starts take 4-9 s.
  `/health` is unguarded, so the warm-up works while the kill switch is ON. Repeat it if the first call times out.
- **Memory is capped at 3008 MB on this account.** 3008 MB / 2 threads is the chosen config; see
  [backend_capacity.md](backend_capacity.md) for the measurements and the free-tier math.
- The first image push uploads the ~1 GB model layer (took 33 min on this connection). Later pushes reuse it.
- Benchmarks change the function's memory and environment directly; restore the template values afterwards
  (3008 MB, `LLAMA_THREADS=2`, no `LLAMA_EXTRA`) or redeploy.

Stacks: `codegen-persistent` (DynamoDB, retained), `codegen-ecr` (image repo, keeps the newest 2), `codegen-backend`.
Tear down with `infra\teardown.ps1` (backend only) or `-All`.

Function URL: `https://sug6pvql5qkkk3tm7udviuyoc40jwvys.lambda-url.eu-north-1.on.aws/` (POST `/generate`, GET `/health`).

## Tests

- `python -m pytest backend/tests` with DynamoDB Local on :8000: guard logic (11 tests).
- `python backend/tests/e2e_local.py <image>`: the real app, real model, DynamoDB Local (16 checks).
- `infra/scripts/live_tests_model.py`: the same guardrails against the deployed function.

## Known limits

- `/health` is unguarded (the Web Adapter needs it). It costs about 3 ms per call.
- Anonymous limits key on the last `x-forwarded-for` entry; not yet checked against spoofing on a real Function URL.
- Function URL changes made out of band propagate slowly (see above).
- Not yet verified: whether a function idle for days or weeks pays the ~75 s image fetch again on its next cold start.
