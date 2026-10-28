import { useMemo, useState } from "react";
import { extractCode, suggestFilename, tokenize, unusedImports } from "@/lib/python";
import { RunState, active, waking } from "@/lib/runMachine";

// onPlay: offered in the empty state, so a first look at the page has an obvious next step where the output goes.
export function Listing({ run, onPlay }: { run: RunState; onPlay: () => void }) {
  const code = useMemo(() => extractCode(run.text), [run.text]);
  const toks = useMemo(() => tokenize(code), [code]);
  const finished = run.phase === "done" || run.phase === "stopped" || run.phase === "error";
  const notes = useMemo(() => (finished ? unusedImports(code) : []), [code, finished]);
  const file = useMemo(() => suggestFilename(code), [code]);
  const [copied, setCopied] = useState(false);
  const lines = code ? code.split("\n").length : 0;
  const noteLines = new Set(notes.map((n) => n.line));

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code + "\n");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; the text is selectable */
    }
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([code + "\n"], { type: "text/x-python" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: file });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="listing" aria-labelledby="j2">
      <div className="listing-head">
        <h2 id="j2" className="silk">
          J2 · Listing out · {code ? file : "—"}
          {run.source === "replay" && run.phase !== "idle" && <span className="sig2 tag" style={{ marginLeft: 8 }}>replay</span>}
        </h2>
        <div className="acts silk">
          <button type="button" onClick={copy} disabled={!code || !finished}>{copied ? "Copied" : "Copy"}</button>
          <button type="button" onClick={save} disabled={!code || !finished}>Save .py</button>
        </div>
      </div>
      <div className="code" aria-busy={active(run)}>
        {code ? (
          <>
            <pre className="gutter" aria-hidden="true">
              {Array.from({ length: lines }, (_, i) => `${noteLines.has(i + 1) ? "◄" : " "}${i + 1}`).join("\n")}
            </pre>
            <pre className="src" aria-label="Generated code">
              <code>
                {toks.map((t, i) => (t.k === "txt" ? t.v : <span key={i} className={`k-${t.k}`}>{t.v}</span>))}
                {active(run) && <span className="caret" aria-hidden="true">▌</span>}
              </code>
            </pre>
          </>
        ) : (
          <div className="empty">
            {run.phase === "idle" ? (
              <div className="empty-idle">
                <p>Nothing generated yet. The code appears here token by token, at the speed the model wrote it on Lambda.</p>
                <button type="button" className="btn-ghost silk" onClick={onPlay}>Play a recorded run ▸</button>
              </div>
            ) : waking(run) ? (
              <p className="waking">Waking up the model… The first request after a quiet spell starts a fresh copy on AWS
                Lambda (usually 5–10 s). The code streams here as soon as it is ready.</p>
            ) : run.phase === "connecting" ? "waiting for first token…" : "No code in the response."}
          </div>
        )}
      </div>
      <div className="listing-foot">
        <span>{lines} lines · {run.done?.tokens ?? run.tokenTimes.length} tokens</span>
        {notes.map((n) => (
          <span key={`${n.line}${n.text}`}><span className="tp">N · L{n.line}</span> {n.text} <span className="dim">(naive check; model output is unedited)</span></span>
        ))}
        {run.phase === "stopped" && <span className="tp">stopped early: output is partial</span>}
      </div>
    </section>
  );
}
