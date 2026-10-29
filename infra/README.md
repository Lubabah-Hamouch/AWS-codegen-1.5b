# infra

AWS infrastructure as CloudFormation templates, deployed with the AWS SAM CLI (`sam deploy`; settings in
`samconfig.toml`). Region eu-north-1.

| Stack | Template | Contents |
|---|---|---|
| `codegen-persistent` | `persistent.yaml` | DynamoDB table `codegen-state`: quotas, slots, kill flag, hashed API keys (retained on delete) |
| `codegen-ecr` | `ecr.yaml` | Image repository, keeps the newest 2 images |
| `codegen-backend` | `backend.yaml` | Lambda (arm64, 3008 MB, container image), streaming Function URL, CORS, daily warm-up rule, invocation alarm, SNS topic and the circuit-breaker Lambda |
| `codegen-frontend` | `frontend.yaml` | Private S3 site bucket, CloudFront with origin access control, CSP and security headers |

| Script | Purpose |
|---|---|
| `scripts/build_push.ps1` | Build the arm64 image with buildx and push it to ECR |
| `scripts/seed_state.py` | Seed limits, create the demo key, set the kill flag, write `status.json` |
| `scripts/killswitch.ps1` | Pause or resume the backend (kill flag plus Function URL auth) |
| `scripts/live_tests_model.py` | Live checks against the deployed model: guardrails, error codes, SSE, CORS, status.json |
| `scripts/live_tests_hardening.py` | Live checks: client-IP spoofing, warm-up rule, circuit breaker |
| `scripts/live_tests_private.py` | The same guardrails with the Function URL kept locked to the public: SigV4-signed requests; `--breaker` trips the circuit breaker with real traffic |
| `scripts/signing_proxy.py` | Local-only proxy that signs the playground's requests, so the real UI can be tested against the backend while the URL stays locked |
| `scripts/bench_lambda.py`, `scripts/bench_coldstart.py` | Memory/thread and cold-start benchmarks behind [docs/backend_capacity.md](../docs/backend_capacity.md) |
| `teardown.ps1` | Delete the backend stack, or everything with `-All` |

Deploy order, the going-live checklist, the kill switch and the live test suites are in
[docs/runbook.md](../docs/runbook.md). The live tests and benchmarks spend real Lambda time; the runbook says when to
run them.
