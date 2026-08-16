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
import os
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = {}  # populated in main(): {prefix: target_base}


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

    def do_POST(self):
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
    global ROUTES
    p = argparse.ArgumentParser(description="Serve xVector with Kinetica + Ollama proxies.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--kinetica", default=os.environ.get("KINETICA_URL", "http://localhost:9191"),
                   help="Kinetica instance URL")
    p.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                   help="Ollama base URL")
    args = p.parse_args()
    ROUTES = {"/kinetica": args.kinetica, "/ollama": args.ollama}

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("xVector   http://%s:%d" % (args.host, args.port))
    print("Kinetica  %s  →  proxied at /kinetica" % args.kinetica)
    print("Ollama    %s  →  proxied at /ollama" % args.ollama)
    print("Set the app's Instance URL to /kinetica\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
