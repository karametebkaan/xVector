#!/usr/bin/env python3
"""Serve xVector and proxy SQL to Kinetica from the same origin.

    python3 scripts/serve.py
    python3 scripts/serve.py --port 8080 --kinetica http://kinetica-host:9191

Open the printed URL, then set the app's Instance URL to /kinetica. Requests to
/kinetica/execute/sql are forwarded to the real instance, so the browser never makes a
cross-origin call and neither CORS nor mixed-content blocking applies.

Standard library only. No dependencies, no install.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = {}  # populated in main(): {prefix: target_base}
CLAUDE_BIN = "claude"


def resolve_upstream(path, routes):
    """Rewrite an incoming path to its upstream URL for the longest matching
    route prefix. Returns None when no prefix matches (caller serves it
    locally or 404s)."""
    best = None
    for prefix, target in routes.items():
        if path == prefix or path.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, target)
    if best is None:
        return None
    prefix, target = best
    return target.rstrip("/") + path[len(prefix):]


def _default_run(cmd, stdin_bytes, timeout):
    return subprocess.run(cmd, input=stdin_bytes, capture_output=True, timeout=timeout)


def run_claude(prompt, schema, model, claude_bin="claude", timeout=180, _run=None):
    """Shell the claude CLI (stored login) for one schema-constrained call.
    Returns {"status":"OK","data":<structured_output>} or {"status":"ERROR","message":...}."""
    cmd = [claude_bin, "-p", "--output-format", "json"]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    if model:
        cmd += ["--model", model]
    run = _run or _default_run
    try:
        proc = run(cmd, (prompt or "").encode(), timeout)
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "message": "claude CLI timed out after %ds" % timeout}
    except FileNotFoundError:
        return {"status": "ERROR", "message": "claude CLI not found (set --claude-bin)"}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "message": "claude CLI failed: %s" % e}
    try:
        obj = json.loads((proc.stdout or b"").decode() or "{}")
    except Exception:  # noqa: BLE001
        tail = ((proc.stderr or b"") or (proc.stdout or b"")).decode(errors="replace")[:400]
        return {"status": "ERROR", "message": "claude CLI non-JSON output: %s" % tail}
    if proc.returncode != 0 or obj.get("is_error"):
        return {"status": "ERROR", "message": obj.get("result") or "claude CLI error"}
    so = obj.get("structured_output")
    if so is None:
        return {"status": "ERROR", "message": "claude CLI returned no structured_output"}
    return {"status": "OK", "data": so}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _proxy(self, method, url, body):
        req = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        auth = self.headers.get("Authorization")
        if auth:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                payload, status = res.read(), res.status
        except urllib.error.HTTPError as e:
            payload, status = e.read(), e.code
        except Exception as e:
            msg = ('{"status":"ERROR","message":"proxy could not reach %s: %s"}'
                   % (url, str(e).replace('"', "'")))
            payload, status = msg.encode(), 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw or b"{}")

    def _send_json(self, status, obj):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _claude(self):
        try:
            req = self._read_json()
        except Exception as e:  # noqa: BLE001
            return self._send_json(400, {"status": "ERROR", "message": "bad request body: %s" % e})
        out = run_claude(req.get("prompt") or "", req.get("schema"),
                         req.get("model") or "", claude_bin=CLAUDE_BIN)
        self._send_json(200 if out.get("status") != "ERROR" else 502, out)

    def do_POST(self):
        if self.path == "/claude":
            return self._claude()
        url = resolve_upstream(self.path, ROUTES)
        if url is None:
            self.send_error(404, "No proxy route for %s" % self.path)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self._proxy("POST", url, body)

    def do_GET(self):
        url = resolve_upstream(self.path, ROUTES)
        if url is None:
            return super().do_GET()  # serve static files
        self._proxy("GET", url, None)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    global ROUTES, CLAUDE_BIN
    p = argparse.ArgumentParser(description="Serve xVector with Kinetica + Ollama proxies.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--kinetica", default=os.environ.get("KINETICA_URL", "http://localhost:9191"),
                   help="Kinetica instance URL")
    p.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                   help="Ollama base URL")
    p.add_argument("--claude-bin", default=os.environ.get("CLAUDE_BIN", "claude"),
                   help="Path to the claude CLI binary")
    args = p.parse_args()
    ROUTES = {"/kinetica": args.kinetica, "/ollama": args.ollama}
    CLAUDE_BIN = args.claude_bin

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("xVector   http://%s:%d" % (args.host, args.port))
    print("Kinetica  %s  →  proxied at /kinetica" % args.kinetica)
    print("Ollama    %s  →  proxied at /ollama" % args.ollama)
    print("Claude    %s  →  /claude (stored login)" % args.claude_bin)
    print("Set the app's Instance URL to /kinetica\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
