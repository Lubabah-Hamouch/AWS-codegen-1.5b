# model-artifacts

Local working folder for model files (adapters, merged weights, GGUF exports). **Everything here except this README is
gitignored**; model weights are never committed.

**The fine-tuned model is not published anywhere public.** The shipped Q4_K_M GGUF (986 MB) exists only inside the
backend's container image in a private ECR repository, where the Lambda function loads it. There is no download.

To get the model, reproduce it:

- [training/README.md](../training/README.md): the path from the source prompts to the QLoRA adapter, the merge, the
  GGUF export and the HumanEval numbers.
- [docs/model_card.md](../docs/model_card.md): exact specs (base model, data, LoRA settings, checkpoint, llama.cpp
  build, file sizes) and limitations.
