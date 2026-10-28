// Measured numbers, one place. Sources: docs/eval_report.md, docs/model_card.md, docs/backend_capacity.md
// (all measured 2026-10-28). Anything shown as "bench" in the UI comes from here, not from the current run.

// Public address of the site (CloudFront); link previews need absolute URLs.
export const SITE = "https://d2js86b0xg0ozs.cloudfront.net";

export const MODEL = {
  name: "qwen2.5-coder-1.5b-ft",
  base: "Qwen2.5-Coder-1.5B-Instruct",
  quant: "Q4_K_M",
  sizeMb: 986,
  runtime: "llama.cpp b11856",
  promptVersion: "generate.v1",
  ctx: 2048,
  maxTokens: 512,
  decode: "greedy · top_k 1 · seed 42",
};

export const HOST = {
  target: "Lambda arm64 (Graviton2)",
  region: "eu-north-1",
  memoryMb: 3008,
  threads: 2,
  rssIdleMb: 2087,
  rssPeakMb: 2117,
  coldStart: "4–9 s",
  coldStart3008: "4.3–4.9 s",
  firstStartNewImage: "~75–90 s (once per new image, absorbed by the deploy warm-up)",
};

export const PERF = {
  tokS: 15.9,
  tokSSpread: [11.7, 19.1] as const,
  billedS: 9.5,
  gbS: 27.8,
  initS: "3.4–3.8 s",
};

export const BUDGET = {
  anonPerIp: 5,
  globalDaily: 100,
  anonTotalDaily: 50,
  concurrency: 2,
  freeTierGbS: 400000,
  genPerMonthWarm: 14400,
  genPerMonthCold: 10200,
  worstCaseGbS: 329000,
  breakerPer5Min: 600,
};

export const EVAL = {
  humaneval: 64.0,
  humanevalPlus: 61.0,
  formatClean: 98.8, // 162/164; was 99.4 before the type-hint import check (docs/eval_report.md, 2026-10-28)
  eos: 100,
  meanTokens: 167,
  noisePt: 7,
  // the base model, same prompt and scoring (base bf16 column below)
  base: { humaneval: 65.2, formatClean: 5.5, meanTokens: 300, proseAfter: 154 },
  tasks: 164,
  // rows: [label, base bf16, merged bf16, Q4_K_M GGUF (shipped)]
  exported: [
    ["HumanEval pass@1", "65.2% (107/164)", "70.1% (115/164)", "64.0% (105/164)"],
    ["HumanEval+ pass@1", "59.1% (97/164)", "66.5% (109/164)", "61.0% (100/164)"],
    ["Format-clean", "5.5% (9/164)", "100% (164/164)", "98.8% (162/164)"],
    ["Stopped on its own", "99.4%", "100%", "100%"],
    ["Mean response tokens", "300", "167", "167"],
  ],
  formatFailures: [
    ["Prose after the code block", "154", "0"],
    ["Prose before the code block", "53", "0"],
    ["Missing return type hint", "115", "0"],
    ["Type-hint name not imported", "0", "1"],
    ["Missing parameter type hint", "104", "0"],
    ["Missing docstring", "98", "0"],
  ],
  paired: [
    ["merged bf16 vs base bf16", "HumanEval", "23", "15", "0.26"],
    ["merged bf16 vs base bf16", "HumanEval+", "26", "14", "0.08"],
    ["Q4_K_M vs merged bf16", "HumanEval", "12", "22", "0.12"],
    ["Q4_K_M vs merged bf16", "HumanEval+", "13", "22", "0.18"],
  ],
};

export const TRAINING = {
  examples: 4535,
  pipeline: "50,661 rows → 14,042 with tests → 6,000 sampled ×4 → 12,963 passed checks → 4,535 SFT examples",
  lora: "r 16 · α 32 · dropout 0.05 · 7 projections · 18.46M params",
  optim: "lr 2e-4 cosine · batch 16 · NF4 QLoRA",
  checkpoint: "step 250 / 273 (0.91 epochs), val loss 0.1299",
};

export const EXAMPLES = [
  "Write a Python function that returns the nth Fibonacci number.",
  "Write a function that checks whether a string is a palindrome, ignoring case and punctuation.",
  "Write a function that merges overlapping intervals in a list of (start, end) tuples.",
  "Write a function that converts a Roman numeral string to an integer.",
  "Write a function that groups a list of words into anagram groups.",
];
