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
import re
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = {}  # populated in main(): {prefix: target_base}
GCP_PROJECT = ""
GCP_REGION = "global"
CLAUDE_MODEL_DEFAULT = "claude-haiku-4-5-20251001"


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


def _vertex_model_id(model):
    """Vertex names dated models `alias@YYYYMMDD`; undated aliases pass through.
    `claude-haiku-4-5-20251001` -> `claude-haiku-4-5@20251001`; `claude-opus-4-8`
    unchanged. Without this the publisher endpoint 404s on a dated id."""
    return re.sub(r"-(\d{8})$", r"@\1", model or "")


def _extract_json(text):
    """Return the first complete JSON object/array embedded in text, or None.
    Tolerates markdown fences and trailing prose by scanning for a value the
    strict decoder can consume — the model is prompted for JSON, not forced."""
    if not text:
        return None
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
            return obj
        except ValueError:
            continue
    return None


def run_claude(prompt, schema, model, project, region="global", timeout=180,
               _token=None, _post=None):
    """One Anthropic-on-Vertex call via REST (rawPredict) using an ADC access
    token. The prompt carries the JSON contract; we parse the returned text
    (schema is the parse-JSON signal, not server-enforced). Returns
    {"status":"OK","data":<obj|text>} or {"status":"ERROR","message":...}."""
    token = _token if _token is not None else _gcloud_token()
    if not token:
        return {"status": "ERROR", "message": "no gcloud token — run `gcloud auth application-default login`"}
    vid = _vertex_model_id(model or CLAUDE_MODEL_DEFAULT)
    if not re.match(r"^[\w.@-]+$", vid):
        return {"status": "ERROR", "message": "invalid model"}
    loc = region or "global"
    host = "aiplatform.googleapis.com" if loc == "global" else "%s-aiplatform.googleapis.com" % loc
    url = ("https://%s/v1/projects/%s/locations/%s/publishers/anthropic/models/%s:rawPredict"
           % (host, project, loc, vid))
    body = json.dumps({
        "anthropic_version": "vertex-2023-10-16",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8192,
    }).encode()
    post = _post or _default_post
    try:
        raw = post(url, body, token, timeout)
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "message": "Claude request failed: %s" % e}
    try:
        obj = json.loads((raw or b"").decode())
    except Exception:  # noqa: BLE001
        return {"status": "ERROR", "message": "Claude non-JSON response: %s" % (raw or b"")[:300]}
    if isinstance(obj, list):
        obj = obj[0] if obj else {}   # Vertex may wrap the message in a 1-element list
    if isinstance(obj, dict) and "error" in obj:
        err = obj["error"]
        return {"status": "ERROR", "message": str(err.get("message") if isinstance(err, dict) else err)}
    try:
        blocks = obj["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except Exception:  # noqa: BLE001
        return {"status": "ERROR", "message": "Claude unexpected shape: %s" % json.dumps(obj)[:300]}
    if schema is None:
        return {"status": "OK", "data": text}
    data = _extract_json(text)
    if data is None:
        return {"status": "ERROR", "message": "Claude content was not JSON: %s" % str(text)[:300]}
    return {"status": "OK", "data": data}


def _gcloud_token():
    """Access token for Vertex. Prefers Application Default Credentials; falls
    back to the user-login token if ADC is unset."""
    for cmd in (["gcloud", "auth", "application-default", "print-access-token"],
                ["gcloud", "auth", "print-access-token"]):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            continue
        if p.returncode == 0:
            tok = (p.stdout or b"").decode().strip()
            if tok:
                return tok
    return None


def _gcloud_project():
    try:
        p = subprocess.run(["gcloud", "config", "get-value", "project"],
                           capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        return ""
    val = (p.stdout or b"").decode().strip()
    return "" if val in ("", "(unset)") else val


def _default_post(url, body, token, timeout):
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        return e.read()


def run_gemini(prompt, model, project, region="global", timeout=180, _token=None, _post=None):
    """One Gemini call via Vertex REST using a gcloud access token. The prompt
    carries the JSON contract; we ask for a JSON mime-type and parse the text.
    Returns {"status":"OK","data":<obj>} or {"status":"ERROR","message":...}."""
    token = _token if _token is not None else _gcloud_token()
    if not token:
        return {"status": "ERROR", "message": "no gcloud token — run `gcloud auth login`"}
    if not re.match(r"^[\w.-]+$", model or ""):
        return {"status": "ERROR", "message": "invalid model"}
    loc = region or "global"
    host = "aiplatform.googleapis.com" if loc == "global" else "%s-aiplatform.googleapis.com" % loc
    url = ("https://%s/v1/projects/%s/locations/%s/publishers/google/models/%s:generateContent"
           % (host, project, loc, model))
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }).encode()
    post = _post or _default_post
    try:
        raw = post(url, body, token, timeout)
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "message": "Gemini request failed: %s" % e}
    try:
        obj = json.loads((raw or b"").decode())
    except Exception:  # noqa: BLE001
        return {"status": "ERROR", "message": "Gemini non-JSON response: %s" % (raw or b"")[:300]}
    if isinstance(obj, dict) and "error" in obj:
        err = obj["error"]
        return {"status": "ERROR", "message": str(err.get("message") if isinstance(err, dict) else err)}
    try:
        text = obj["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:  # noqa: BLE001
        return {"status": "ERROR", "message": "Gemini unexpected shape: %s" % json.dumps(obj)[:300]}
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return {"status": "ERROR", "message": "Gemini content was not JSON: %s" % str(text)[:300]}
    return {"status": "OK", "data": data}


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
                         req.get("model") or "", GCP_PROJECT, GCP_REGION)
        self._send_json(200 if out.get("status") != "ERROR" else 502, out)

    def _gemini(self):
        try:
            req = self._read_json()
        except Exception as e:  # noqa: BLE001
            return self._send_json(400, {"status": "ERROR", "message": "bad request body: %s" % e})
        out = run_gemini(req.get("prompt") or "", req.get("model") or "",
                         GCP_PROJECT, GCP_REGION)
        self._send_json(200 if out.get("status") != "ERROR" else 502, out)

    def do_POST(self):
        if self.path == "/claude":
            return self._claude()
        if self.path == "/gemini":
            return self._gemini()
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
    global ROUTES, GCP_PROJECT, GCP_REGION
    p = argparse.ArgumentParser(description="Serve xVector with Kinetica + Ollama proxies.")
    p.add_argument("--port", type=int, default=8181)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--kinetica", default=os.environ.get("KINETICA_URL", "http://localhost:9191"),
                   help="Kinetica instance URL")
    p.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                   help="Ollama base URL")
    p.add_argument("--gcp-project",
                   default=(os.environ.get("GOOGLE_CLOUD_PROJECT")
                            or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID") or ""),
                   help="GCP project for Claude/Gemini on Vertex (default: gcloud config project)")
    p.add_argument("--gcp-region",
                   default=(os.environ.get("GOOGLE_CLOUD_LOCATION")
                            or os.environ.get("CLOUD_ML_REGION") or "global"),
                   help="Vertex region for Claude/Gemini")
    args = p.parse_args()
    ROUTES = {"/kinetica": args.kinetica, "/ollama": args.ollama}
    GCP_PROJECT = args.gcp_project or _gcloud_project()
    GCP_REGION = args.gcp_region

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("xVector   http://%s:%d" % (args.host, args.port))
    print("Kinetica  %s  →  proxied at /kinetica" % args.kinetica)
    print("Ollama    %s  →  proxied at /ollama" % args.ollama)
    print("Claude    Vertex %s/%s  →  /claude (ADC)" % (GCP_PROJECT or "?", GCP_REGION))
    print("Gemini    Vertex %s/%s  →  /gemini (ADC)" % (GCP_PROJECT or "?", GCP_REGION))
    print("Set the app's Instance URL to /kinetica\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
