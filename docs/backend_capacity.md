# Backend capacity and cost: measured on Lambda arm64 (eu-north-1)

Model: Qwen2.5-Coder-1.5B fine-tune, Q4_K_M GGUF (986 MB), llama.cpp b11856 cross-compiled for Graviton2
(`armv8.2-a+dotprod+fp16`), behind the Lambda Web Adapter. Measured 2026-10-28. Raw data:
[bench_coldstart_results.json](bench_coldstart_results.json) (clean run used below) and
[bench_lambda_results.json](bench_lambda_results.json) (first run; its 1536 MB row is contaminated, see the note at the end).

This account caps Lambda memory at **3008 MB**, so the planned 3.5 GB and 6 GB configurations could not be tested.

## Results per configuration

3 forced cold starts per configuration (new execution environment, same image), each followed by 2 warm generations
(~145 tokens on average, the typical response length; the HumanEval mean was 167).

| | 1536 MB, 1 thread | 2048 MB, 1 thread | **3008 MB, 2 threads** | 3008 MB, 2 threads, `--no-repack` |
|---|---|---|---|---|
| Cold start, `/health` end to end | 6.3 / 7.9 / 7.7 s | 5.5 / 7.4 / 9.0 s | **4.9 / 4.3 / 4.4 s** | 3.8 / 2.7 / 3.7 s |
| Init Duration (billed) | 4.4 / 5.6 / 5.6 s | 4.0 / 5.0 / 7.1 s | **3.4 / 3.8 / 3.4 s** | 2.8 / 1.9 / 2.9 s |
| Init timeouts (>10 s) | 0 | 0 | **0** | 0 |
| Generation speed (warm) | 8.8 tok/s | 10.3 tok/s | **15.9 tok/s** | 11.3 tok/s |
| Billed time per generation | 17.0 s | 15.7 s | **9.5 s** | 13.7 s |
| **GB-seconds per generation** | 25.4 | 31.4 | **27.8** | 40.1 |
| Memory used, idle / peak | 1531 / 1532 MB (at the limit) | 2044 / 2044 MB (at the limit) | **2087 / 2117 MB** | 1150 / 1181 MB |

**Chosen: 3008 MB, 2 threads.** It costs about 9% more GB-s per generation than 1536 MB but answers nearly twice as fast
(9.5 s vs 17 s for a typical response) and has the shortest cold start. The 1536 and 2048 MB configurations run pinned at
their memory limit, which is why they are slower than their CPU share alone would predict.

Weight repacking roughly doubles memory (a converted copy of the weights next to the mmap'd file) and buys 40% more speed.
`--no-repack` starts ~1 s faster but costs 44% more GB-s per generation, so repacking stays on.

### Speed in context (same model, greedy)

| Where | tok/s |
|---|---|
| WSL, 12 threads, x86 desktop (Phase 3) | 19.1 |
| Docker x86, 2 CPUs (Spike 2) | 14-17 |
| **Lambda Graviton2, 3008 MB (~1.7 vCPU), 2 threads** | **15.9** |
| Lambda Graviton2, 1 thread | 8.8-11.0 |

Speed varies by execution environment: in one minute, three environments of the same 3008 MB / 2-thread function
generated at 19.1, 15.8 and 11.7 tok/s (a different host CPU or neighbour load is the likely cause; Lambda does not
say which). 15.9 tok/s is the median across the benchmark; plan for a 12-19 tok/s spread per request. The free-tier
math below uses the median.

## Cold starts

- **With the image cached, cold starts are 4-9 s to ready**, and every one of 12 forced cold starts stayed inside Lambda's
  10 s init window. At 3008 MB a user waits about **5.5-6 s for the first token** after a cold start
  (4.3-4.9 s to ready plus ~1 s time to first token), then ~16 tok/s.
- **The ~75 s start is a one-time cost after deploying a new image.** The first request after `codegen-backend` was created
  took 91 s end to end: the init phase hit the 10 s limit (`INIT_REPORT ... Status: timeout`), Lambda retried init inside
  the invocation, and the model needed ~76 s to become ready while the 1 GB image was fetched for the first time. No later
  cold start came near that: 15 cold starts with the same image (3 in the first benchmark, 12 in the clean run) all took
  4-9 s. So the expensive part is the first fetch of a new image, not the cold start itself.
- **It is the model layer that costs the time.** A later deploy that changed only the app layer (model layer unchanged)
  started in 11 s on its first request.
- **Idle periods: insured, not verified.** AWS documents that idle functions can become `Inactive` (the first invocation
  then fails while Lambda re-creates resources) but does not document cache eviction for idle container images. Rather than
  wait to find out, a daily EventBridge warm-up now invokes the function once a day (~340 GB-s/month); its CloudWatch
  REPORT lines show the cold-start time each day, so a recurrence of the long start would be visible there.
- That 91 s first request is right at the 90 s function timeout, so it must not be a user's request: the runbook's deploy
  step now includes a warm-up call to `/health` (unguarded, works while the kill switch is ON).

## Free-tier ceiling (replaces the 1,600-2,700/month estimate)

Lambda free tier: 1M requests and 400,000 GB-s per month. INIT time is billed. At 3008 MB (2.94 GB):

| Scenario | GB-s per generation | Generations / month within 400,000 GB-s |
|---|---|---|
| Typical response (~145 tokens), warm | 27.8 | **~14,400** (~480/day) |
| Typical response, every request a cold start (+~11 GB-s init) | 39.1 | **~10,200** (~340/day) |
| Maximum response (512 tokens, ~33.5 s), warm | 98.4 | ~4,060 |
| Maximum response, every request a cold start | 109.7 | ~3,650 |

**The realistic ceiling is ~10,000-14,000 generations/month, 4-9x the original 1,600-2,700 estimate.** Requests (1M) are
not the binding limit.

The guardrails keep the account inside the free tier even in the worst case: `global_daily = 100` allows at most ~3,000
generations/month, and 3,000 maximum-length cold generations cost ~329,000 GB-s, under 400,000. Raising `global_daily`
above ~120 removes that worst-case guarantee; ~340/day is the limit for typical traffic if every request is cold.

Other costs: one-time ~270 GB-s per new image deploy (the 91 s first start); ECR storage for 2 images of ~1 GB
(~$0.10/GB-month beyond any free allowance); DynamoDB stays inside the always-free 25 RCU/WCU (table is 10/15).

## If cold starts need to go down later

Not needed at current numbers, recorded for the decision log:

| Option | Effect | Cost / tradeoff |
|---|---|---|
| Post-deploy warm-up call (done) | Removes the one-time ~75 s start from users | None |
| Daily warm-up invocation, EventBridge rule (done) | Keeps the function from going idle for weeks, in case that evicts the image | ~1 cold start/day = ~340 GB-s/month |
| SnapStart for container images (opt-in label for custom runtimes, launched 2026-07) | Restores a snapshot with the model loaded instead of loading it; AWS claims sub-second | Breaks $0: ~$11.50/month snapshot caching at 3008 MB + ~$0.0004 per restore; untested with a llama-server subprocess and the Web Adapter |
| Provisioned concurrency, 1 environment | No cold starts at all | Breaks $0: ~$32/month at 3008 MB, and the free tier does not apply to that function |

Prices are AWS's published US example rates; Arm is roughly 20% lower.

## Note on the first benchmark run

`bench_lambda_results.json` came from `bench_lambda.py`, whose 1536 MB pass started while the out-of-band kill test's
auth change was still propagating: its first two requests got 403 from AWS and never reached the function, and its
CloudWatch window had no end time, so lines from later configurations leaked into it. Its 2048 and 3008 MB rows agree with
the clean run. The table above uses only the clean `bench_coldstart.py` run.
