import Head from "next/head";
import Link from "next/link";
import type { ReactNode } from "react";
import { Footer, Masthead } from "@/components/Masthead";
import { BUDGET, EVAL, HOST, MODEL, PERF, TRAINING } from "@/data/facts";

const SECTIONS = [
  ["overview", "Overview"],
  ["interface", "Interface"],
  ["runtime", "Runtime characteristics"],
  ["eval", "Evaluation"],
  ["capacity", "Capacity and cost"],
  ["guard", "Guardrails"],
  ["training", "Training"],
  ["limits", "Limitations"],
  ["replay", "Replay mode"],
] as const;

function Sec({ id, title, rev, children }: { id: string; title: string; rev?: string; children: ReactNode }) {
  const n = SECTIONS.findIndex(([s]) => s === id) + 1;
  return (
    <section id={id} className="sec" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="silk"><span className="n">§{n}</span>{title}{rev && <span className="r">{rev}</span>}</h2>
      <div className="body">{children}</div>
    </section>
  );
}

function Table({ caption, head, rows, num = [], ship }: { caption?: string; head: string[]; rows: (string | number)[][]; num?: number[]; ship?: number }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>{head.map((h, i) => <th key={h} scope="col" className={num.includes(i) ? "num" : ""}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r[0]) + String(r[1])}>
              {r.map((c, i) => i === 0
                ? <th key={i} scope="row" style={{ fontWeight: 400 }}>{c}</th>
                : <td key={i} className={`${num.includes(i) ? "num" : ""}${i === ship ? " ship" : ""}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Bars({ label, items, max = 100, unit = "%" }: { label: string; items: [string, number, boolean?][]; max?: number; unit?: string }) {
  return (
    <figure className="bars" style={{ margin: 0 }} aria-label={label}>
      <figcaption className="dim" style={{ fontSize: 11 }}>{label}</figcaption>
      {items.map(([name, v, ship]) => (
        <div className="bar" key={name} title={`${name}: ${v.toFixed(1)}${unit}`}>
          <span>{name}</span>
          <span className="track" aria-hidden="true"><span className={`fill${ship ? " ship" : ""}`} style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="v">{v.toFixed(1)}{unit}</span>
        </div>
      ))}
    </figure>
  );
}

const PINOUT = `POST /generate                      content-type: application/json
  { "prompt": "<1..2000 chars>",   "max_tokens": <1..512, optional> }

200  text/event-stream
  event: token   data: {"t": "<text>"}                       one per decoded token
  event: done    data: {"finish_reason", "tokens", "prompt_tokens",
                        "tok_s", "ttft_s", "prompt_version", "remaining"}
  event: error   data: {"error", "code": "generation_failed"}

4xx/5xx  application/json  {"error": "<for humans>", "code": "<stable>"}   retry-after on 429`;

export default function Notes() {
  return (
    <>
      <Head>
        <title>Codegen-1.5B · datasheet</title>
      </Head>
      <main className="page">
        <Masthead page="datasheet" />
        <div className="ds">
          <nav className="toc" aria-label="Contents">
            <h2 className="silk">Contents</h2>
            <ol>
              {SECTIONS.map(([id, t], i) => (
                <li key={id}><a href={`#${id}`}><span>§{i + 1}</span>{t}</a></li>
              ))}
            </ol>
          </nav>

          <div>
            <Sec id="overview" title="Overview" rev="measured 2026-10-28">
              <p>
                A QLoRA fine-tune of {MODEL.base} that answers a request for a Python function with exactly one fenced
                block, with a docstring and full type hints, and then stops. It is a format adaptation, not a capability upgrade:
                format compliance went from 5.5% to {EVAL.formatClean}%, while correctness stayed level with the base model.
              </p>
              <ul>
                <li>Shipped as a {MODEL.quant} GGUF ({MODEL.sizeMb} MB), served by {MODEL.runtime} on {HOST.target}, {HOST.memoryMb} MB, {HOST.threads} threads.</li>
                <li>Tokens stream over server-sent events from a Lambda Function URL; the browser calls it directly.</li>
                <li>Runs inside the AWS free tier by construction: daily caps, a concurrency cap, a kill switch and an invocation circuit breaker.</li>
                <li>{PERF.tokS} tok/s median decode, {HOST.coldStart} cold start, {PERF.gbS} GB·s per typical generation.</li>
              </ul>
            </Sec>

            <Sec id="interface" title="Interface">
              <pre className="pinout">{PINOUT}</pre>
              <Table
                caption="Error codes: the playground branches on code, never on the message"
                head={["code", "status", "meaning", "what the playground does"]}
                rows={[
                  ["busy", "429", "both generation slots in use", "Retry button after retry-after (2 s)"],
                  ["daily_limit", "429", "your 5 live runs today are used", "offers recorded runs; resets 00:00 UTC"],
                  ["daily_capacity", "429", "the site-wide daily budget is spent", "offers recorded runs"],
                  ["disabled", "503", "kill switch on", "switches to replay mode"],
                  ["unavailable", "503", "guard failed closed (state store unreachable)", "switches to replay mode"],
                  ["starting", "503", "model still loading", "Retry after 5 s"],
                  ["bad_request / too_large", "400 / 413", "invalid prompt or body", "message shown inline"],
                  ["(no response)", "—", "network, or URL locked to AWS_IAM (403 without CORS)", "treated as paused"],
                ]}
              />
            </Sec>

            <Sec id="runtime" title="Runtime characteristics" rev={`${HOST.memoryMb} MB · ${HOST.threads} threads · ${HOST.region}`}>
              <Table
                head={["parameter", "min", "typ", "max", "unit", "condition"]}
                num={[1, 2, 3]}
                rows={[
                  ["decode rate", PERF.tokSSpread[0], PERF.tokS, PERF.tokSSpread[1], "tok/s", "per execution environment; host CPU varies"],
                  ["cold start, to ready", "4.3", "4.4", "4.9", "s", "image cached; 4–9 s across all tested configs, all inside the 10 s init window"],
                  ["first start, new image", "", "75–90", "", "s", "once per deploy; absorbed by the deploy warm-up"],
                  ["init duration, billed", "3.4", "3.4", "3.8", "s", "3008 MB"],
                  ["billed time per generation", "", PERF.billedS, "33.5", "s", "typ ~145 tokens; max 512 tokens"],
                  ["GB-seconds per generation", "", PERF.gbS, "98.4", "GB·s", "warm; +~11 GB·s if cold"],
                  ["memory, idle / peak", "", HOST.rssIdleMb, HOST.rssPeakMb, "MB", `of ${HOST.memoryMb} MB`],
                  ["context / max output", "", MODEL.ctx, MODEL.maxTokens, "tokens", "server caps max_tokens at 512"],
                ]}
              />
              <Table
                caption="Memory and thread configurations (3 forced cold starts each, then 2 warm generations)"
                head={["config", "cold start s", "tok/s", "billed s/gen", "GB·s/gen", "memory MB"]}
                num={[2, 3, 4]}
                rows={[
                  ["1536 MB, 1 thread", "6.3 / 7.9 / 7.7", "8.8", "17.0", "25.4", "1532 (at limit)"],
                  ["2048 MB, 1 thread", "5.5 / 7.4 / 9.0", "10.3", "15.7", "31.4", "2044 (at limit)"],
                  ["▸ 3008 MB, 2 threads (chosen)", "4.9 / 4.3 / 4.4", "15.9", "9.5", "27.8", "2087 / 2117"],
                  ["3008 MB, 2 threads, --no-repack", "3.8 / 2.7 / 3.7", "11.3", "13.7", "40.1", "1150 / 1181"],
                ]}
              />
            </Sec>

            <Sec id="eval" title="Evaluation" rev="HumanEval / HumanEval+ · 164 tasks · greedy pass@1">
              <Bars label="HumanEval pass@1 (the shipped GGUF is highlighted)"
                items={[["base bf16", 65.2], ["merged bf16", 70.1], ["Q4_K_M GGUF (shipped)", 64.0, true]]} />
              <Bars label="Format-clean responses: one block, docstring, type hints, clean stop"
                items={[["base bf16", 5.5], ["merged bf16", 100], ["Q4_K_M GGUF (shipped)", 99.4, true]]} />
              <Table head={["", "base bf16", "merged bf16", "Q4_K_M GGUF (shipped)"]} rows={EVAL.exported} num={[1, 2, 3]} ship={3} />
              <p>
                Read it as: <strong>the format was learned and correctness did not move.</strong> With 164 tasks one pass@1
                figure carries about ±7 points of noise. Quantising to Q4_K_M costs ~6 points against the merged bf16 model
                (not significant at this n, but consistent with the 4-bit penalty measured on the base) and leaves the shipped
                model level with the original base, now in the target format.
              </p>
              <Table caption="Paired comparison per task (exact McNemar)" head={["comparison", "benchmark", "only first passes", "only second passes", "p"]}
                rows={EVAL.paired} num={[2, 3, 4]} />
              <Table caption="Format failures, base bf16 vs fine-tune (a response can have several)" head={["check", "base bf16", "fine-tune"]}
                rows={EVAL.formatFailures} num={[1, 2]} />
              <p className="dim">
                Contamination check: no training example copies a benchmark problem or solution (lexical, structural and 8-gram checks);
                some topical overlap on classics (Fibonacci, Roman numerals). Excluding the overlapping tasks moves pass@1 by at most 0.7 points.
              </p>
            </Sec>

            <Sec id="capacity" title="Capacity and cost" rev="Lambda free tier: 400,000 GB·s and 1M requests per month">
              <Table head={["scenario", "GB·s / generation", "generations / month within free tier"]} num={[1, 2]}
                rows={[
                  ["typical (~145 tokens), warm", "27.8", "~14,400 (~480/day)"],
                  ["typical, every request cold", "39.1", "~10,200 (~340/day)"],
                  ["maximum (512 tokens), warm", "98.4", "~4,060"],
                  ["maximum, every request cold", "109.7", "~3,650"],
                ]} />
              <p>
                The global cap of {BUDGET.globalDaily} generations/day bounds the worst month at ~3,000 maximum-length cold generations
                ≈ {BUDGET.worstCaseGbS.toLocaleString("en-US")} GB·s, under the 400,000 free tier. Requests are not the binding limit.
                Rejected requests are still billed invocations, which is why the circuit breaker exists.
              </p>
            </Sec>

            <Sec id="guard" title="Guardrails" rev="every check fails closed">
              <ul>
                <li><strong>Kill switch, two layers.</strong> A DynamoDB flag the app checks on every request (immediate), and switching the Function URL to AWS_IAM auth so AWS rejects requests before invoking anything (35–41 s to propagate).</li>
                <li><strong>Daily quotas.</strong> {BUDGET.anonPerIp} runs per visitor IP, {BUDGET.anonTotalDaily} for all anonymous visitors, {BUDGET.globalDaily} site-wide; one conditional DynamoDB transaction, so a refused request consumes nothing. The IP comes from AWS's request context, not a spoofable header.</li>
                <li><strong>Concurrency.</strong> {BUDGET.concurrency} generation slots as expiring leases, so a crashed invocation cannot leak capacity.</li>
                <li><strong>Circuit breaker.</strong> More than {BUDGET.breakerPer5Min} invocations in 5 minutes trips a CloudWatch alarm; a small Lambda sets the kill flag, writes status.json and locks the URL.</li>
                <li><strong>status.json.</strong> Written next to this site by the kill-switch tooling and the breaker, served uncached; the playground reads it on load and shows replays instead of making requests that would fail.</li>
              </ul>
            </Sec>

            <Sec id="training" title="Training" rev="model card">
              <Table head={["", ""]} rows={[
                ["base model", `${MODEL.base} (Apache-2.0)`],
                ["prompt source", "bigcode/self-oss-instruct-sc2-exec-filter-50k, instruction column only (ODC-By)"],
                ["responses", "generated by the base model under a format system prompt, then assert-executed in a sandbox"],
                ["data pipeline", TRAINING.pipeline],
                ["method", TRAINING.optim],
                ["LoRA", TRAINING.lora],
                ["checkpoint", TRAINING.checkpoint],
                ["export", "merged into bf16, logits verified, GGUF f16 → Q4_K_M (llama.cpp b11856)"],
                ["serving prompt", `${MODEL.promptVersion}: the request as the only user message, no system prompt`],
              ]} />
            </Sec>

            <Sec id="limits" title="Limitations">
              <ul>
                <li>1.5B parameters: expect subtle logic errors and wrong edge cases. Every output here is unreviewed model output.</li>
                <li>It always answers with one code block, even when asked for prose or for another language.</li>
                <li>One benchmark family, one greedy sample per task; the format checks are this project's own.</li>
                <li>Decode speed depends on which Lambda host serves the request (11.7–19.1 tok/s observed).</li>
                <li>Lambda memory is capped at 3008 MB on this account; larger configurations were not testable.</li>
              </ul>
            </Sec>

            <Sec id="replay" title="Replay mode">
              <p>
                When live generation is paused, over budget or unreachable, the playground plays recorded runs instead. Each recording is a
                real response from the deployed model (same image, same prompt template, greedy decoding), captured with the arrival time of
                every token and replayed with that timing. Replays are labelled wherever they appear, make no backend call, and use no quota.
                They are recorded by <code>frontend/scripts/record_replays.py</code>.
              </p>
              <p><Link href="/">← back to the playground</Link></p>
            </Sec>
          </div>
        </div>
        <Footer />
      </main>
    </>
  );
}
