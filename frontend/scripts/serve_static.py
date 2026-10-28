"""Serve the static export (out/) the way CloudFront does: directory URLs -> index.html, 404.html, a parked status.json, the site's CSP
and security headers (read from infra/frontend.yaml), and correct types for .mjs / .wasm.

    python frontend/scripts/serve_static.py [port]        then  BASE_URL=http://127.0.0.1:3999 npx playwright test
"""

import http.server
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
API = "https://sug6pvql5qkkk3tm7udviuyoc40jwvys.lambda-url.eu-north-1.on.aws"
yaml = (ROOT.parent / "infra" / "frontend.yaml").read_text(encoding="utf-8")
CSP = re.search(r'- "(default-src[^"]+)"', yaml).group(1).replace("${Origin}", API.split("://")[1])


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".json": "application/json"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(OUT), **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("content-security-policy", CSP)
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("x-frame-options", "DENY")
        super().end_headers()

    def send_head(self):
        if self.path.split("?")[0] == "/status.json":  # the bucket's copy is not in out/; serve the parked state
            body = b'{"live": false, "since": "local", "note": "paused"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        path = self.translate_path(self.path)
        if not Path(path).exists() and not self.path.split("?")[0].endswith("/"):
            if Path(path + "/index.html").exists():
                self.path += "/"
        if not Path(self.translate_path(self.path)).exists():
            body = (OUT / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().send_head()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3999
    print(f"http://127.0.0.1:{port}  CSP: {CSP}", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
