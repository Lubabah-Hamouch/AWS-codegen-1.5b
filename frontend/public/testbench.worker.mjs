// Test bench worker: runs generated Python with Pyodide (CPython on WebAssembly) inside a Web Worker.
// One worker per run: the page terminates it afterwards (or on timeout), so nothing a run does can leak into the next.
// Containment is the browser's: no real filesystem (Pyodide's is in memory), network limited by the site's CSP
// (connect-src: this site and the Function URL), and the page kills the worker when the time limit passes.
// A plain file served from /, not bundled: it imports the self-hosted runtime from /pyodide/.

import { loadPyodide } from "/pyodide/pyodide.mjs";

const HARNESS = String.raw`
import ast, contextlib, io, json, re, sys

def _norm(kind, v):
    if kind == "tuples":
        return [tuple(x) for x in v]
    if kind == "groups":
        groups = v.values() if isinstance(v, dict) else v
        return sorted(sorted(g) for g in groups)
    return v

def _err(e):
    tb = e.__traceback__
    line = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "generated.py":
            line = tb.tb_lineno
        tb = tb.tb_next
    return {"type": type(e).__name__, "msg": str(e)[:300], "line": line}

def _bench(code, suite_json):
    suite = json.loads(suite_json) if suite_json else None
    res = {"python": sys.version.split()[0], "stage": "parse", "defined": [], "target": None,
           "stdout": "", "error": None, "checks": []}
    try:
        tree = ast.parse(code, "generated.py")
    except SyntaxError as e:
        res["error"] = {"type": "SyntaxError", "msg": e.msg, "line": e.lineno}
        return json.dumps(res)
    funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    res["defined"] = funcs + [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    ns = {"__name__": "generated"}
    out = io.StringIO()
    res["stage"] = "exec"
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(tree, "generated.py", "exec"), ns)
    except BaseException as e:
        res["error"] = _err(e)
        res["stdout"] = out.getvalue()[-2000:]
        return json.dumps(res)
    res["stage"] = "done"
    if suite and funcs:
        pat = re.compile(suite["match"], re.I)
        target = next((n for n in funcs if pat.search(n)), funcs[0])
        res["target"] = target
        env = dict(ns, f=ns[target])
        for c in suite["checks"]:
            row = {"call": c["call"], "expect": c["expect"], "ok": False, "got": None, "error": None}
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    got = eval(c["call"], env)
                row["got"] = repr(got)[:200]
                kind = c.get("norm")
                row["ok"] = _norm(kind, got) == _norm(kind, eval(c["expect"], {}))
            except BaseException as e:
                row["error"] = _err(e)
            res["checks"].append(row)
    res["stdout"] = out.getvalue()[-2000:]
    return json.dumps(res)
`;

const ready = (async () => {
  const py = await loadPyodide({ indexURL: "/pyodide/", stdin: () => null });
  py.runPython(HARNESS);
  return py;
})();

ready.then(
  () => postMessage({ type: "ready" }),
  (e) => postMessage({ type: "boot_failed", message: String(e) }),
);

self.onmessage = async ({ data }) => {
  const py = await ready;
  const bench = py.globals.get("_bench");
  try {
    const out = bench(data.code, data.suite ? JSON.stringify(data.suite) : "");
    postMessage({ type: "result", result: JSON.parse(out) });
  } catch (e) {
    postMessage({ type: "boot_failed", message: String(e) });
  } finally {
    bench.destroy();
  }
};
