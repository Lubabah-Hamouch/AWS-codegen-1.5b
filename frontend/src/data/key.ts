// Plain-language names for the schematic's labels: the one-line subtitle under each block and the "How to read"
// key both come from here, so they cannot drift apart.

export const PLAIN = {
  u1: "Your request: pick an example, or type your own when live",
  u2: "Decides whether a live request may run: kill switch, quotas, concurrency",
  u3: "The fine-tuned model, running on AWS Lambda",
  u4: "The answer arrives token by token as it is generated",
  u5: "How the shipped model scores on a standard coding benchmark",
  r1: "The limits that keep this demo at $0",
  u6: "Runs checks on the generated code, here in your browser",
} as const;

export const LEGEND: { term: string; means: string }[] = [
  { term: "U1–U6 · units", means: "The stages a request passes through, left to right, then the evaluation and the test bench." },
  { term: "J1, J2 · jacks", means: "Where text enters (your prompt) and where it leaves (the generated code)." },
  { term: "TP1–TP4 · test points", means: "Live measurements of the current run: time to first token, speed, length, how it ended." },
  { term: "R1 · reference", means: "The budget the guardrails enforce." },
  { term: "bench", means: "A number measured in benchmarks, not by the run on screen." },
  { term: "replay", means: "The output is a recording of a real run, not generated now; no request reaches the backend." },
  { term: "Moving wires", means: "Data flowing during a run (they stay still if you prefer reduced motion)." },
];
