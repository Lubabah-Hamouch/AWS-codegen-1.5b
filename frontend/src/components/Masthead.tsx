import Link from "next/link";
import { HOST, MODEL } from "@/data/facts";
import { ThemePicker } from "./ThemePicker";

export function Masthead({ page }: { page: "schematic" | "datasheet" }) {
  return (
    <>
    <a className="skip" href={page === "schematic" ? "#controls" : "#overview"}>Skip to {page === "schematic" ? "controls" : "content"}</a>
    <header className="mast">
      <div className="mast-title">
        <span className="silk dim" style={{ fontSize: 11 }}>
          {page === "schematic" ? "Fine-tuned Python listing generator · signal path" : "Datasheet · model, evaluation, capacity"}
        </span>
        <h1 className="silk">
          <Link href="/">Codegen<span className="cu">-</span>1.5B</Link>
        </h1>
        <span className="dim" style={{ fontSize: 12 }}>
          {MODEL.base} + QLoRA → {MODEL.quant} → llama.cpp on Lambda arm64, $0 budget
        </span>
      </div>
      <div className="mast-side">
        <div className="mast-bar">
          <nav aria-label="Sections" className="mast-nav silk">
            <Link href="/" aria-current={page === "schematic" ? "page" : undefined}>Schematic</Link>
            <Link href="/notes/" aria-current={page === "datasheet" ? "page" : undefined}>Datasheet</Link>
          </nav>
          <ThemePicker />
        </div>
        <table className="tblock">
          <tbody>
            <tr>
              <td><span className="k silk">Dwg</span>CG-PLAYGROUND-01</td>
              <td><span className="k silk">Rev</span>C</td>
              <td><span className="k silk">Sheet</span>{page === "schematic" ? "1 / 2" : "2 / 2"}</td>
            </tr>
            <tr>
              <td><span className="k silk">Target</span>λ arm64 · {HOST.memoryMb} MB</td>
              <td><span className="k silk">Region</span>{HOST.region}</td>
              <td><span className="k silk">Prompt</span>{MODEL.promptVersion}</td>
            </tr>
            <tr>
              <td><span className="k silk">Model</span>{MODEL.quant} · {MODEL.sizeMb} MB</td>
              <td><span className="k silk">Runtime</span>b11856</td>
              <td><span className="k silk">Decode</span>greedy</td>
            </tr>
          </tbody>
        </table>
      </div>
    </header>
    </>
  );
}

export function Footer() {
  return (
    <footer className="foot">
      <span>Qwen2.5-Coder-1.5B-Instruct (Apache-2.0) fine-tuned on self-oss-instruct prompts (ODC-By). Outputs are unreviewed model output, with one automatic fix: missing typing imports are added and marked.</span>
      <span><Link href="/notes/">Datasheet</Link> · theme <kbd>Shift</kbd>+<kbd>T</kbd></span>
    </footer>
  );
}
