"""Local-only proxy that SigV4-signs requests to the Function URL, so the real playground UI can talk to the backend
while the URL stays locked (AWS_IAM) to everyone else. Used by frontend/tests/e2e/private-live.spec.ts.

    python infra/scripts/signing_proxy.py [port]       listens on 127.0.0.1 only (default 8787)

Forwards GET /health and POST /generate with the operator's credentials (profile codegen-spike). Responses are passed
back as they arrive, so streaming still streams. It opens nothing: the app kill switch decides whether generations run.
"""

import http.server
import sys
import urllib.error
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

S = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
URL = S.client("lambda").get_function_url_config(FunctionName="codegen-backend")["FunctionUrl"].rstrip("/")
CREDS = S.get_credentials().get_frozen_credentials()
PASS = ("content-type", "retry-after")


class H(http.server.BaseHTTPRequestHandler):
    def _forward(self, method: str):
        if self.path not in ("/health", "/generate"):
            return self.send_error(404)
        body = self.rfile.read(int(self.headers.get("content-length", 0))) if method == "POST" else None
        headers = {"content-type": "application/json"} if body else {}
        req = AWSRequest(method=method, url=URL + self.path, data=body, headers=headers)
        SigV4Auth(CREDS, "lambda", "eu-north-1").add_auth(req)
        try:
            resp = urllib.request.urlopen(urllib.request.Request(URL + self.path, data=body, method=method,
                                                                 headers=dict(req.headers)), timeout=120)
        except urllib.error.HTTPError as e:
            resp = e
        self.send_response(resp.status if hasattr(resp, "status") else resp.code)
        for k, v in resp.headers.items():
            if k.lower() in PASS:
                self.send_header(k, v)
        self.end_headers()
        while chunk := resp.read1(4096) if hasattr(resp, "read1") else resp.read(4096):
            self.wfile.write(chunk)
            self.wfile.flush()

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def log_message(self, fmt, *args):
        print("proxy:", fmt % args, flush=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    print(f"signing proxy on http://127.0.0.1:{port} -> {URL}", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
