import Link from "next/link";
import { COMPARE } from "@/data/compare";
import { EVAL } from "@/data/facts";
import type { SiteStatus } from "@/lib/status";

// The on-ramp: what this is, what to do, and the result, in plain words. The schematic below is the detailed view.

const FAILURE: Record<string, string> = {
  prose_before: "prose before the code",
  prose_after: "prose after the code",
  missing_docstring: "no docstring",
  missing_param_hints: "no parameter types",
  missing_return_hint: "no return type",
};

type Props = { status: SiteStatus; playing: boolean; onWatch: () => void };

export function Intro({ status, playing, onWatch }: Props) {
  return (
    <section className="intro" aria-labelledby="intro-h">
      <div className="intro-main">
        <h2 id="intro-h" className="intro-lead">
          A code model fine-tuned to almost always answer in one clean, typed, documented function, deployed to AWS
          for $0.
        </h2>
        <ol className="intro-steps">
          <li><span className="n silk">1</span>Pick an example prompt</li>
          <li><span className="n silk">2</span>Watch a real recorded run, at its original speed</li>
          <li><span className="n silk">3</span>Run checks on the code, right in your browser</li>
        </ol>
        <div className="runrow">
          <button type="button" className="btn-run silk" onClick={onWatch} disabled={playing}>
            {playing ? "Playing…" : "Watch a recorded run ▸"}
          </button>
          <Link href="/notes/">How it was built →</Link>
        </div>
        {status.live === false && (
          <p className="intro-status" role="status">
            <strong className="silk sig2">{status.note === "circuit breaker" ? "Paused by circuit breaker" : "Live generation paused"}</strong>{" "}
            {status.note === "circuit breaker" ? "A traffic spike tripped the breaker. " : status.note === "unreachable" ? "The backend did not answer. " : "The backend is parked to keep it at $0. "}
            Replays are real outputs recorded from the deployed model, played back with their original token timing.
          </p>
        )}
      </div>

      <div className="intro-result">
        <h3 className="silk">What fine-tuning changed</h3>
        <table className="result">
          <caption className="sr-only">Base model compared with the fine-tuned model as shipped, HumanEval, {EVAL.tasks} problems</caption>
          <thead>
            <tr><th scope="col"><span className="sr-only">Measure</span></th><th scope="col" className="dim">base</th><th scope="col" className="dim">fine-tuned</th></tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Clean answers<small>just the code: typed, documented, no chatter</small></th>
              <td>{EVAL.base.formatClean}%</td><td className="au big">{EVAL.formatClean}%</td>
            </tr>
            <tr className="flat">
              <th scope="row">Correct answers<small className="said">about the same: within ±{EVAL.noisePt} pt noise (HumanEval pass@1)</small></th>
              <td>{EVAL.base.humaneval}%</td><td>{EVAL.humaneval.toFixed(1)}%</td>
            </tr>
            <tr>
              <th scope="row">Answer length<small>mean tokens per answer</small></th>
              <td>{EVAL.base.meanTokens}</td><td className="big">{EVAL.meanTokens}</td>
            </tr>
          </tbody>
        </table>
        <p className="dim intro-fine">
          Same {EVAL.tasks} HumanEval problems and prompt for both; fine-tuned on one 8 GB GPU, shipped 4-bit.{" "}
          <Link href="/notes/#eval">Full evaluation →</Link>
        </p>
      </div>

      <details className="compare">
        <summary className="silk">Before / after: one real answer from the evaluation</summary>
        <p className="dim">
          {COMPARE.taskId}, the same prompt for both, greedy decoding. Both answers are correct; the difference is the
          shape of the answer. Typical rather than worst case: {EVAL.base.proseAfter} of {EVAL.tasks} base answers had
          prose after the code. Shown exactly as generated.
        </p>
        <details className="compare-prompt">
          <summary>The prompt</summary>
          <pre>{COMPARE.userMessage}</pre>
        </details>
        <div className="compare-cols">
          <Answer title="Base model" sub="Qwen2.5-Coder-1.5B-Instruct" a={COMPARE.base} />
          <Answer title="Fine-tuned, as shipped" sub="4-bit GGUF, the model on this page" a={COMPARE.shipped} />
        </div>
      </details>
    </section>
  );
}

type A = (typeof COMPARE)["base"] | (typeof COMPARE)["shipped"];

function Answer({ title, sub, a }: { title: string; sub: string; a: A }) {
  const fails: readonly string[] = a.formatFailures;
  return (
    <figure className="answer">
      <figcaption>
        <strong className="silk">{title}</strong> <span className="dim">{sub} · {a.tokens} tokens</span>
        <span className="answer-tags">
          <span className={a.passHumanEval && a.passHumanEvalPlus ? "sig2" : "tp"}>
            {a.passHumanEval && a.passHumanEvalPlus ? "✓ passes HumanEval and HumanEval+" : "✗ fails the tests"}
          </span>
          <span className={fails.length ? "tp" : "sig2"}>
            {fails.length ? `✗ format: ${fails.map((f) => FAILURE[f] ?? f).join(", ")}` : "✓ format clean"}
          </span>
        </span>
      </figcaption>
      <pre tabIndex={0} aria-label={`${title} answer`}>{a.response}</pre>
    </figure>
  );
}
