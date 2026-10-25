# aws-code-playground

> **Status: under construction.** This repository is being rebuilt from scratch.
> Nothing here is deployed yet, and the sections below describe the plan, not a finished product.

A code-generation playground: you describe a task, a small code language model writes the
code back, streamed to the browser. The model is a small open code LLM fine-tuned locally with
QLoRA on a consumer GPU, evaluated with a reproducible base-vs-fine-tuned benchmark, and served
from AWS using only free-tier-eligible services. The deployment is designed to cost $0 to run,
with hard usage caps so a traffic spike cannot turn into a bill.

## Repository layout

| Folder | Purpose |
|---|---|
| [`training/`](training/) | Local QLoRA fine-tuning scripts, configs and the evaluation harness |
| [`model-artifacts/`](model-artifacts/) | Local-only model files (gitignored) |
| [`backend/`](backend/) | Lambda handler, llama.cpp packaging, prompt templates |
| [`infra/`](infra/) | AWS CDK app and stacks |
| [`frontend/`](frontend/) | Next.js app |
| [`docs/`](docs/) | Architecture diagram, evaluation reports, README assets |

## Architecture

_To be filled in once the design is built and measured._

## Roadmap

1. Local fine-tuning pipeline
2. Reproducible evaluation (base vs fine-tuned)
3. Model export and versioned storage
4. Backend, tested locally
5. Next.js frontend
6. AWS deployment
7. CI/CD and observability

## License

To be confirmed.
