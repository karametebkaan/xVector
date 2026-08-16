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
PREFIX = "/kinetica"
TARGET = "http://localhost:9191"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def do_POST(self):
        if not self.path.startswith(PREFIX):
            self.send_error(404, "Only %s/* accepts POST" % PREFIX)
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        url = TARGET.rstrip("/") + self.path[len(PREFIX):]

        req = urllib.request.Request(url, data=body, method="POST")
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
                   % (TARGET, str(e).replace('"', "'")))
            payload, status = msg.encode(), 502

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    global TARGET
    p = argparse.ArgumentParser(description="Serve xVector with a Kinetica proxy.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--kinetica", default=os.environ.get("KINETICA_URL", TARGET),
                   help="Kinetica instance URL (default %s)" % TARGET)
    args = p.parse_args()
    TARGET = args.kinetica

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("xVector   http://%s:%d" % (args.host, args.port))
    print("Kinetica  %s  →  proxied at %s" % (TARGET, PREFIX))
    print("Set the app's Instance URL to %s\n" % PREFIX)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
