# backend

The Lambda app: a small Python HTTP server that admits each request through the guardrails, then streams tokens from
llama.cpp's `llama-server` as server-sent events. It runs in a container image behind the AWS Lambda Web Adapter.

| Path | Contents |
|---|---|
| `app/main.py` | `POST /generate` (SSE) and `GET /health`; input validation, error codes, starts and supervises `llama-server` |
| `app/guard.py` | Admission control in DynamoDB: kill switch, per-IP and global daily quotas, API keys, 2 concurrency slots |
| `app/prompts.py` | The `generate.v1` prompt template |
| `Dockerfile` | arm64 image: llama.cpp b11856 cross-compiled, the Q4_K_M GGUF, the app. Its header lists the two inputs that are not in git (`vendor/`, `model/`) |
| `tests/test_guard.py` | Guard unit tests against DynamoDB Local |
| `tests/e2e_local.py` | End-to-end checks of the real container (x86 build) against DynamoDB Local |
| `bench/local_bench.py` | Local Docker timing: cold start, time to first token, tokens/s (x86; not representative of Graviton) |

## Test

```bash
docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
DDB_ENDPOINT=http://localhost:8000 python -m pytest backend/tests -q    # guard tests (skipped if DynamoDB Local is down; REQUIRE_DDB=1 fails instead, as in CI)
python backend/tests/e2e_local.py IMAGE                                 # needs an x86 build of the Dockerfile
```

The API contract (request, events, error codes) is on the site's `/notes` page, §2. Building, deploying and the live
test suites against the real Function URL are in [docs/runbook.md](../docs/runbook.md); measured speed, cold starts and
cost are in [docs/backend_capacity.md](../docs/backend_capacity.md).
