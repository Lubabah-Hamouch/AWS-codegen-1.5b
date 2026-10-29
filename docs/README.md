# docs

| File | Contents |
|---|---|
| [eval_report.md](eval_report.md) | HumanEval / HumanEval+ for base, fine-tuned bf16 and the shipped Q4_K_M GGUF; format checks, paired tests, contamination check; failure analysis, tuple-immutability probe, the shipped typing-import fix (model output vs as served) |
| [model_card.md](model_card.md) | The shipped model: training data, settings, intended use, limits |
| [backend_capacity.md](backend_capacity.md) | Lambda memory/thread choice, speed, cold starts and the free-tier ceiling, all measured |
| [bench_lambda_results.json](bench_lambda_results.json), [bench_coldstart_results.json](bench_coldstart_results.json) | Raw benchmark data behind backend_capacity.md |
| [runbook.md](runbook.md) | Operating the deployment: going live, pausing, deploying, recording replays, tests |
| [assets/](assets/) | Screenshots used in the top-level README (taken 2026-10-29 from the live site) |
