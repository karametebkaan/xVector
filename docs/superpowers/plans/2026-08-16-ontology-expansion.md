# SP2 Ontology Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand xVector from two entity types (Person/Business) to the five-type ontology (People, Business, Organization, Facility, Location), add LLM-extracted typed *relation* edges alongside the existing embedding-similarity edges (two-layer multigraph), and drive real-LLM extraction through new Claude and Gemini providers (Ollama chat extraction retired).

**Architecture:** All app logic stays in `index.html` (vanilla JS, no deps). Pure DOM-free logic lives inside `/* CORE:BEGIN … CORE:END */` markers and is unit-tested by `scripts/test_graph.mjs` (`node --test`). Credentials never reach the browser: cloud LLM calls go through two new same-origin proxy routes in `scripts/serve.py` (stdlib `subprocess` + `urllib`), mirroring `/kinetica` and `/ollama`. `/claude` shells the `claude` CLI stored login; `/gemini` uses a `gcloud` Vertex token. Tested by `scripts/test_serve.py`.

**Tech Stack:** HTML/CSS/vanilla JS (single file); Python 3 stdlib (`scripts/serve.py`); `node --test` and Python `unittest` harnesses; Claude CLI (Vertex stored login); Gemini via Vertex REST.

**Spec:** `docs/superpowers/specs/2026-08-16-ontology-expansion-design.md`

## Global Constraints

- Single file for app code: `index.html`. No deps/CDN/localStorage/build. `scripts/` stays stdlib-only.
- `DIM` stays `64`, never a UI field.
- User-facing strings go through `log(msg, cls)` — `ok`/`err`/`warn`/`dim`.
- SQL escaping via `esc()`; floats via `num()` (6 decimals); table/entity names via `guardName()` (CHAR(64) cap).
- Pure DOM-free logic lives inside `/* CORE:BEGIN … CORE:END */` so `scripts/test_graph.mjs` can extract and eval it. The eval context exposes only: `Math, Map, Set, Array, JSON, String, Number, Date, isNaN, parseInt, parseFloat, Float64Array, RegExp, Object`. Do not reference `document`/`window`/`fetch` inside CORE.
- LLM structured output is schema-constrained per provider (Claude `--json-schema`; Gemini `responseMimeType:"application/json"` + prompt-embedded enum). All providers share the same CORE post-processing guards (`foldExtraction`).
- Credentials never reach the browser. Cloud LLM calls go through `scripts/serve.py` proxy routes.
- Canonical-name-is-stable rule (append mode): a node's PK name never changes; new variants become aliases.
- Canonical label token is **`"People"`** (not `"Person"`) across the five-type set.

## Planner Rulings (settled here — do not re-litigate)

1. **Edge PK uses a scalar `edge_label CHAR(32)`.** The spec (§7.2) leaves open whether Kinetica can PK on an ARRAY element and requires the first edge task to decide. Ruling: use a scalar `edge_label CHAR(32)` column mirroring the array element, key on `(node1, node2, edge_label)`, and keep the ARRAY `label VARCHAR[]` for display/graph. This avoids any live dependency on ARRAY-PK support. Cost if wrong: a slightly wider edge table than strictly necessary — harmless.
2. **Gemini uses `responseMimeType` only, no `responseSchema`.** babelgraph's own Gemini path omits `responseSchema` (dialect quirks: no `$ref`, restricted keywords) and relies on the prompt + JSON-extract. Ruling: mirror that — `/gemini` sends `responseMimeType:"application/json"` + a prompt that spells out the enum and JSON shape; the CORE guards are the safety net. Claude keeps the real `--json-schema`. Cost if wrong: Gemini occasionally returns an off-enum label — folded by `normLabel`/`normPredicate` anyway.
3. **Extraction providers are `local`, `claude`, `gemini` only.** The OpenAI-compatible `llm` chat option and the Ollama chat option are both removed from the extraction dropdown (spec §2.1, user decision). Ollama *embeddings* and the `/ollama` proxy route stay untouched. Cost if wrong: a user wanting a generic OpenAI chat endpoint loses it — re-addable later.

## File Structure

- `scripts/serve.py` — add `/claude` and `/gemini` POST handlers + `run_claude()`/`run_gemini()` module functions + `--claude-bin`/`--gcp-project`/`--gcp-region` flags. (Tasks 1-2)
- `scripts/test_serve.py` — unit tests for the new route functions with injected fakes. (Tasks 1-2)
- `index.html` — CORE: type system, disambiguation, edges, emitters, extraction folding, relation edges (Tasks 3-7); DOM: extraction UI + transport, integration/rendering (Tasks 8-9).
- `scripts/test_graph.mjs` — extend/rewrite CORE tests (Tasks 3-7).
- `sql/schema.sql`, `SETUP.md`, `CLAUDE.md` — docs kept in sync (Task 10).

---

## Task 1: serve.py `/claude` route

**Files:**
- Modify: `scripts/serve.py`
- Test: `scripts/test_serve.py`

**Interfaces:**
- Produces: `run_claude(prompt, schema, model, claude_bin="claude", timeout=180, _run=None) -> dict` returning `{"status":"OK","data":<obj>}` or `{"status":"ERROR","message":<str>}`. `do_POST` intercepts `path == "/claude"`. Module global `CLAUDE_BIN`. Helpers `_default_run(cmd, stdin_bytes, timeout)`, `_read_json(self)`, `_send_json(self, status, obj)`.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_serve.py` (keep existing imports; add `import json`, `import types` at top):

```python
class RunClaude(unittest.TestCase):
    def _fake_run(self, returncode, stdout, stderr=b""):
        def run(cmd, stdin_bytes, timeout):
            self.captured = {"cmd": cmd, "stdin": stdin_bytes, "timeout": timeout}
            return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        return run

    def test_success_returns_structured_output(self):
        out = json.dumps({"is_error": False, "structured_output": {"entities": [], "relations": []}}).encode()
        r = serve.run_claude("hi", {"type": "object"}, "claude-haiku-4-5-20251001", _run=self._fake_run(0, out))
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"], {"entities": [], "relations": []})
        self.assertIn("--json-schema", self.captured["cmd"])
        self.assertIn("--model", self.captured["cmd"])
        self.assertEqual(self.captured["stdin"], b"hi")

    def test_no_schema_omits_flag(self):
        out = json.dumps({"is_error": False, "structured_output": {}}).encode()
        serve.run_claude("hi", None, "", _run=self._fake_run(0, out))
        self.assertNotIn("--json-schema", self.captured["cmd"])
        self.assertNotIn("--model", self.captured["cmd"])

    def test_is_error_true_returns_error(self):
        out = json.dumps({"is_error": True, "result": "model not found"}).encode()
        r = serve.run_claude("hi", None, "bad", _run=self._fake_run(1, out))
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("model not found", r["message"])

    def test_non_json_stdout_returns_error(self):
        r = serve.run_claude("hi", None, "m", _run=self._fake_run(0, b"not json", b"boom"))
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("non-JSON", r["message"])

    def test_missing_structured_output_returns_error(self):
        out = json.dumps({"is_error": False}).encode()
        r = serve.run_claude("hi", None, "m", _run=self._fake_run(0, out))
        self.assertEqual(r["status"], "ERROR")

    def test_binary_not_found_returns_error(self):
        def run(cmd, stdin_bytes, timeout):
            raise FileNotFoundError("no claude")
        r = serve.run_claude("hi", None, "m", _run=run)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("not found", r["message"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/test_serve.py -q` (or `python3 scripts/test_serve.py`)
Expected: FAIL — `AttributeError: module 'serve' has no attribute 'run_claude'`.

- [ ] **Step 3: Implement `run_claude` and the route**

In `scripts/serve.py`, add to the imports block (after `import urllib.request`):

```python
import json
import subprocess
```

Add module globals near `ROUTES = {}`:

```python
CLAUDE_BIN = "claude"
```

Add these module-level functions above `class Handler`:

```python
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
```

Add helper methods inside `class Handler` (place above `do_POST`):

```python
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
```

Modify `do_POST` — add the interception at the very top of the method (before `resolve_upstream`):

```python
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
```

In `main()`, add the flag (after the `--ollama` arg) and set the global (after `ROUTES = ...`):

```python
    p.add_argument("--claude-bin", default=os.environ.get("CLAUDE_BIN", "claude"),
                   help="Path to the claude CLI binary")
```

```python
    global CLAUDE_BIN
    CLAUDE_BIN = args.claude_bin
```

Add a print line in `main()` after the Ollama print:

```python
    print("Claude    %s  →  /claude (stored login)" % args.claude_bin)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 scripts/test_serve.py`
Expected: PASS (existing `ResolveUpstream` + new `RunClaude`).

- [ ] **Step 5: Commit**

```bash
git add scripts/serve.py scripts/test_serve.py
git commit -m "feat(serve): add /claude route shelling the claude CLI for structured extraction"
```

---

## Task 2: serve.py `/gemini` route

**Files:**
- Modify: `scripts/serve.py`
- Test: `scripts/test_serve.py`

**Interfaces:**
- Produces: `run_gemini(prompt, model, project, region="global", timeout=180, _token=None, _post=None) -> dict` returning `{"status":"OK","data":<obj>}` or `{"status":"ERROR","message":...}`. `do_POST` intercepts `path == "/gemini"`. Module globals `GCP_PROJECT`, `GCP_REGION`. Helpers `_gcloud_token()`, `_gcloud_project()`, `_default_post(url, body, token, timeout)`.
- Consumes: `_read_json`/`_send_json` from Task 1.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_serve.py`:

```python
class RunGemini(unittest.TestCase):
    def _gemini_body(self, text):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()

    def test_success_parses_content_json(self):
        captured = {}
        def post(url, body, token, timeout):
            captured["url"] = url; captured["token"] = token
            return self._gemini_body('{"entities":[{"name":"Kaan","label":"People"}],"relations":[]}')
        r = serve.run_gemini("prompt", "gemini-2.5-flash", "proj-x", "global",
                             _token="tok-123", _post=post)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"]["entities"][0]["name"], "Kaan")
        self.assertIn("aiplatform.googleapis.com", captured["url"])
        self.assertIn("projects/proj-x/locations/global", captured["url"])
        self.assertIn("gemini-2.5-flash:generateContent", captured["url"])
        self.assertEqual(captured["token"], "tok-123")

    def test_regional_host(self):
        def post(url, body, token, timeout):
            self.assertTrue(url.startswith("https://us-central1-aiplatform.googleapis.com/"))
            return self._gemini_body("{}")
        serve.run_gemini("p", "m", "proj", "us-central1", _token="t", _post=post)

    def test_no_token_returns_error(self):
        r = serve.run_gemini("p", "m", "proj", "global", _token="", _post=lambda *a: b"{}")
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("gcloud", r["message"])

    def test_google_error_body_surfaces_message(self):
        def post(url, body, token, timeout):
            return json.dumps({"error": {"message": "permission denied"}}).encode()
        r = serve.run_gemini("p", "m", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("permission denied", r["message"])

    def test_content_not_json_returns_error(self):
        def post(url, body, token, timeout):
            return self._gemini_body("this is not json")
        r = serve.run_gemini("p", "m", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("not JSON", r["message"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 scripts/test_serve.py`
Expected: FAIL — `AttributeError: module 'serve' has no attribute 'run_gemini'`.

- [ ] **Step 3: Implement `run_gemini` and the route**

Add `import urllib.error` is already present. Add module globals near `CLAUDE_BIN`:

```python
GCP_PROJECT = ""
GCP_REGION = "global"
```

Add module-level functions above `class Handler`:

```python
def _gcloud_token():
    try:
        p = subprocess.run(["gcloud", "auth", "print-access-token"],
                           capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    if p.returncode != 0:
        return None
    return (p.stdout or b"").decode().strip()


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
```

Add a handler method inside `class Handler` (below `_claude`):

```python
    def _gemini(self):
        try:
            req = self._read_json()
        except Exception as e:  # noqa: BLE001
            return self._send_json(400, {"status": "ERROR", "message": "bad request body: %s" % e})
        out = run_gemini(req.get("prompt") or "", req.get("model") or "",
                         GCP_PROJECT, GCP_REGION)
        self._send_json(200 if out.get("status") != "ERROR" else 502, out)
```

Extend the `do_POST` interception:

```python
        if self.path == "/gemini":
            return self._gemini()
```

In `main()`, add flags (after `--claude-bin`):

```python
    p.add_argument("--gcp-project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
                   help="GCP project for Gemini/Vertex (default: gcloud config project)")
    p.add_argument("--gcp-region", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
                   help="Vertex region for Gemini")
```

Set globals in `main()` (after `CLAUDE_BIN = args.claude_bin`):

```python
    global GCP_PROJECT, GCP_REGION
    GCP_PROJECT = args.gcp_project or _gcloud_project()
    GCP_REGION = args.gcp_region
```

Add a print line after the Claude print:

```python
    print("Gemini    Vertex %s/%s  →  /gemini (gcloud login)" % (GCP_PROJECT or "?", GCP_REGION))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 scripts/test_serve.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/serve.py scripts/test_serve.py
git commit -m "feat(serve): add /gemini route via Vertex REST + gcloud token"
```

---

## Task 3: CORE — five-type system (TYPES, keyword sets, classifySpan, normLabel, normPredicate, palette)

**Files:**
- Modify: `index.html` (CORE block 2 at lines ~742-792 for classify; add TYPES/normLabel/normPredicate; `:root` palette lines 14-16; keyword consts lines 743-746, 795)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Produces (all CORE): `TYPES` object; `normLabel(v)->string`; `normPredicate(v)->string`; `PREDICATES` Set; `classifySpan(nameTokens, personFlag)` now returns one of `People|Business|Organization|Facility|Location` or `null`; keyword sets `BIZ_SUFFIX_WORDS`, `FACILITY_WORDS`, `ORG_WORDS`, `LOCATIONS`. CSS vars `--org`, `--facility`, `--loc`.
- Consumes: `isAcronym`, `bareWord`, `isCap` (existing).

- [ ] **Step 1: Write the failing tests**

In `scripts/test_graph.mjs`, REPLACE the three `extractLocalMentions` label tests (currently lines 33-57) with the block below, and ADD the new tests after them:

```javascript
test("extractLocalMentions finds person and business with title/suffix", () => {
  const m = core.extractLocalMentions([{id:1, text:"Dr Kaan Karamete leads Acme Corp."}]);
  assertNonStrict.deepEqual(m, [
    {surface:"Kaan Karamete", label:"People",   docId:1},
    {surface:"Acme Corp",     label:"Business", docId:1},
  ]);
});

test("extractLocalMentions classifies a university as Organization", () => {
  const m = core.extractLocalMentions([{id:2, text:"The University of Texas hired Jane Doe."}]);
  assertNonStrict.deepEqual(m, [
    {surface:"University of Texas", label:"Organization", docId:2},
    {surface:"Jane Doe",           label:"People",        docId:2},
  ]);
});

test("extractLocalMentions skips bare single tokens, keeps acronyms as business", () => {
  const m = core.extractLocalMentions([{id:3, text:"Zzxq is odd. IBM announced results."}]);
  assertNonStrict.deepEqual(m, [{surface:"IBM", label:"Business", docId:3}]);
});

test("extractLocalMentions accepts title-preceded single surname as person", () => {
  const m = core.extractLocalMentions([{id:4, text:"President Obama spoke."}]);
  assertNonStrict.deepEqual(m, [{surface:"Obama", label:"People", docId:4}]);
});

test("classifySpan returns each of the five types or null", () => {
  const T = (s, flag) => core.classifySpan(s.split(" "), !!flag);
  assert.equal(T("Acme Corp"), "Business");
  assert.equal(T("JFK Airport"), "Facility");
  assert.equal(T("State Department"), "Organization");
  assert.equal(T("Brooklyn"), "Location");           // gazetteer hit
  assert.equal(T("Jane Doe"), "People");
  assert.equal(T("Obama", true), "People");           // title flag, single token
  assert.equal(T("Xylophone"), null);                 // bare single token, no signal
});

test("classifySpan precedence: business suffix beats facility keyword", () => {
  assert.equal(core.classifySpan("Airport Holdings Inc".split(" "), false), "Business");
});

test("normLabel folds synonyms onto the five types", () => {
  assert.equal(core.normLabel("Person"), "People");
  assert.equal(core.normLabel("people"), "People");
  assert.equal(core.normLabel("Business"), "Business");
  assert.equal(core.normLabel("company"), "Business");
  assert.equal(core.normLabel("government agency"), "Organization");
  assert.equal(core.normLabel("university"), "Organization");
  assert.equal(core.normLabel("airport"), "Facility");
  assert.equal(core.normLabel("city"), "Location");
  assert.equal(core.normLabel("weird"), "People");     // default
});

test("normPredicate folds onto the closed vocabulary", () => {
  assert.equal(core.normPredicate("WORKS_AT"), "WORKS_AT");
  assert.equal(core.normPredicate("works at"), "WORKS_AT");
  assert.equal(core.normPredicate("headquartered-in"), "HEADQUARTERED_IN");
  assert.equal(core.normPredicate("mentors"), "RELATED_TO");
  assert.equal(core.normPredicate(""), "RELATED_TO");
});

test("TYPES maps each label to a color var and strategy", () => {
  assert.equal(core.TYPES.People.strategy, "person");
  assert.equal(core.TYPES.Business.strategy, "core");
  assert.equal(core.TYPES.Organization.strategy, "core");
  assert.equal(core.TYPES.Facility.strategy, "norm");
  assert.equal(core.TYPES.Location.strategy, "norm");
  assert.equal(core.TYPES.People.colorVar, "--signal");
  assert.equal(core.TYPES.Location.colorVar, "--loc");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.TYPES`/`core.normLabel`/`core.normPredicate` undefined; classifySpan/extractLocalMentions label mismatches.

- [ ] **Step 3: Add TYPES + keyword sets + normLabel/normPredicate + rewrite classifySpan**

In `index.html`, REPLACE the keyword-set constants at lines 743-746 (the `TITLES`/`ARTICLES`/`BIZ_WORDS`/`CONNECTORS` block, inside CORE block 2) with:

```javascript
const TITLES = new Set(["mr","mrs","ms","miss","dr","prof","professor","president","ceo","cfo","cto","senator","governor","mayor","sir","lord","dame","rev","gen","col","capt","sgt","judge","justice"]);
const ARTICLES = new Set(["the","a","an"]);
const CONNECTORS = new Set(["of","and","the","for","&"]);
// Five-type ontology (single source of truth). colorVar -> :root CSS var; strategy -> disambiguation strategy.
const TYPES = {
  People:       { colorVar:"--signal",   strategy:"person" },
  Business:     { colorVar:"--warm",     strategy:"core"   },
  Organization: { colorVar:"--org",      strategy:"core"   },
  Facility:     { colorVar:"--facility", strategy:"norm"   },
  Location:     { colorVar:"--loc",      strategy:"norm"   },
};
// Local-extractor keyword sets. Precedence: business suffix > facility > org > location > people.
const BIZ_SUFFIX_WORDS = new Set(["inc","llc","ltd","corp","corporation","co","company","gmbh","plc","lp","llp","holdings","partners","ventures","capital"]);
const FACILITY_WORDS = new Set(["airport","stadium","museum","hospital","clinic","hotel","station","mall","plant","factory","library","theater","theatre","arena","center","centre","terminal","port"]);
const ORG_WORDS = new Set(["agency","department","ministry","committee","university","college","institute","school","foundation","association","bank","church","commission","bureau"]);
// Small built-in gazetteer; anything not listed stays null rather than guessing.
const LOCATIONS = new Set(["arlington","brooklyn","manhattan","vienna","paris","london","tokyo","berlin","madrid","rome","moscow","beijing","seattle","boston","denver","austin","dallas","houston","atlanta","miami","texas","california","virginia","germany","france","italy","japan","china","india","canada","mexico","brazil"]);
const PREDICATES = new Set(["WORKS_AT","FOUNDED","LEADS","MEMBER_OF","LOCATED_IN","HEADQUARTERED_IN","PART_OF","OWNS","AFFILIATED_WITH","VISITED","RELATED_TO"]);
function normLabel(v){
  const s = String(v||"").trim().toLowerCase();
  if (s === "people" || s === "person") return "People";
  if (s === "business") return "Business";
  if (s === "organization" || s === "organisation") return "Organization";
  if (s === "facility") return "Facility";
  if (s === "location") return "Location";
  if (/busin|compan|corp|\binc\b|\bllc\b|firm/.test(s)) return "Business";
  if (/organi|agenc|govern|\bngo\b|univers|college|institut|associat|ministr|departmen|committee|foundation|bank|church|school/.test(s)) return "Organization";
  if (/facilit|airport|stadium|hospital|museum|plant|station|venue|arena|terminal|hotel|mall/.test(s)) return "Facility";
  if (/locat|city|country|region|place|town|state|province/.test(s)) return "Location";
  return "People";
}
function normPredicate(v){
  const s = String(v||"").trim().toUpperCase().replace(/[\s-]+/g,"_");
  return PREDICATES.has(s) ? s : "RELATED_TO";
}
```

REPLACE `classifySpan` (lines 752-761) with:

```javascript
function classifySpan(nameTokens, personFlag){
  if (!nameTokens.length) return null;
  const lower = nameTokens.map(t => bareWord(t).toLowerCase());
  const joined = lower.join(" ");
  if (lower.some(t => BIZ_SUFFIX_WORDS.has(t))) return "Business";
  if (lower.some(t => FACILITY_WORDS.has(t)))   return "Facility";
  if (lower.some(t => ORG_WORDS.has(t)))        return "Organization";
  if (LOCATIONS.has(joined))                    return "Location";
  if (nameTokens.length === 1 && isAcronym(bareWord(nameTokens[0]))) return "Business";
  if (personFlag) return "People";
  if (nameTokens.length >= 2) return "People";
  return null;
}
```

- [ ] **Step 4: Update palette in `:root`**

REPLACE lines 14-16 (the `--signal`/`--signal-soft`/`--warm` block) with:

```css
    --signal:#4B2ED6;
    --signal-soft:#EDE9FD;
    --warm:#C97A19;
    --org:#0E7C86;
    --facility:#A6317D;
    --loc:#3B7A2E;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS for the Task 3 tests. NOTE: tests referencing `"Person"` labels in later suites (mergeMentions, blockKey, edge tests) may still FAIL — those are updated in Tasks 4-6. If the harness stops at the first failing file, temporarily confirm the Task 3 tests pass by name; do not "fix" later suites here.

- [ ] **Step 6: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat(core): five-type ontology — TYPES, keyword sets, classifySpan, normLabel/normPredicate, palette"
```

---

## Task 4: CORE — type-aware disambiguation

**Files:**
- Modify: `index.html` (CORE block 3, lines ~795-898)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Consumes: `TYPES` (Task 3), `normalizeName`, `personName`, `businessCore`, `givenCompatible`.
- Produces (CORE, updated behavior): `blockKey(name, label)` and `sameEntity(label, a, b)` now dispatch on `TYPES[label].strategy` (`person`/`core`/`norm`); `mergeMentions` only merges within the same label using the strategy. `resolveIncremental` unchanged in shape (picks up new behavior automatically).

- [ ] **Step 1: Write the failing tests**

In `scripts/test_graph.mjs`: UPDATE the existing `mergeMentions`, `blockKey`, `sameEntity`, and `resolveIncremental` tests to use `"People"` instead of `"Person"` (lines 70-102, 215-258 — every `label:"Person"` → `label:"People"`, and `core.blockKey("Kaan Karamete","People")` etc., and `core.sameEntity("People", …)`). Then ADD:

```javascript
test("blockKey uses the strategy per type", () => {
  assert.equal(core.blockKey("Kaan Karamete", "People"), "karamete");   // person -> surname
  assert.equal(core.blockKey("Acme Corp", "Business"), "acme");         // core -> suffix-stripped
  assert.equal(core.blockKey("State Department", "Organization"), "state department"); // core, no suffix -> normalized
  assert.equal(core.blockKey("JFK Airport", "Facility"), "jfk airport");// norm
  assert.equal(core.blockKey("The Brooklyn", "Location"), "brooklyn");  // norm strips article
});

test("mergeMentions merges within a type by strategy, never across types", () => {
  const biz = core.mergeMentions([
    {surface:"Acme Corp",label:"Business",docId:1},
    {surface:"Acme Inc", label:"Business",docId:2},
  ], "heuristic");
  assert.equal(biz.length, 1);
  // same core string but different labels must NOT merge
  const mixed = core.mergeMentions([
    {surface:"Acme",label:"Business",docId:1},
    {surface:"Acme",label:"Organization",docId:2},
  ], "heuristic");
  assert.equal(mixed.length, 2);
  // two Location surfaces differing only by article merge
  const loc = core.mergeMentions([
    {surface:"Brooklyn",label:"Location",docId:1},
    {surface:"the Brooklyn",label:"Location",docId:2},
  ], "heuristic");
  assert.equal(loc.length, 1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — Location/Organization not handled; `blockKey("…","Organization")` wrong.

- [ ] **Step 3: Make blockKey/sameEntity/mergeMentions strategy-aware**

In `index.html`, REPLACE `sameEntity` (lines 819-828) with:

```javascript
function sameEntity(label, surfaceA, surfaceB){
  const strat = (TYPES[label] && TYPES[label].strategy) || "norm";
  if (strat === "person"){
    const a = personName(surfaceA), b = personName(surfaceB);
    if (a.sur !== b.sur) return false;
    const n = Math.min(a.given.length, b.given.length);
    for (let i=0;i<n;i++) if (!givenCompatible(a.given[i], b.given[i])) return false;
    return true;
  }
  if (strat === "core") return businessCore(surfaceA) === businessCore(surfaceB);
  return normalizeName(surfaceA) === normalizeName(surfaceB);   // norm
}
```

REPLACE `blockKey` (lines 857-860) with:

```javascript
function blockKey(name, label){
  const strat = (TYPES[label] && TYPES[label].strategy) || "norm";
  if (strat === "person") return personName(name).sur;
  if (strat === "core")   return businessCore(name);
  return normalizeName(name);   // norm
}
```

REPLACE the `mergeMentions` merge-decision block (lines 843-848, the `if (m.label === "Person") { put(...) } else { put(...) }`) with a single label-agnostic call:

```javascript
    put(m, b => sameEntity(m.label, b.items[0].surface, m.surface));
```

(Leave the rest of `mergeMentions` — the `none` branch, bucket assembly, and return — unchanged. `businessCore` already falls back to a normalized string when no suffix is present, satisfying the Organization "State Department" case.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS for Task 4 tests (edge-table/emitter suites may still fail — fixed in Tasks 5-6).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat(core): type-aware disambiguation via TYPES strategy (person/core/norm)"
```

---

## Task 5: CORE — two-layer edge shape + schema

**Files:**
- Modify: `index.html` (CORE block 4, lines ~901-979; `graphDdl` edges in CORE block 5, lines ~1004-1012)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Produces (CORE): edge objects now carry `{node1, node2, label, edge_kind, weight, sum_wv, sum_w}` — the old `type` field is retired and `edgeType` is removed. `computeEdges` and `docPairContributions` emit `label:"EMBEDDED", edge_kind:"embedded"`. `graphDdl().edges` gains `edge_label CHAR(32) NOT NULL`, `edge_kind CHAR(16) NOT NULL`, and `PRIMARY KEY (node1, node2, edge_label)`.
- Consumes: `edgeDelta`, `mergeEdgeAccum`, `cosineOf` (unchanged).

- [ ] **Step 1: Write the failing tests**

In `scripts/test_graph.mjs`:
- DELETE the `edgeType orders labels canonically` test (lines 109-114).
- UPDATE the `computeEdges` tests (lines 116-142): remove all `e[0].type` assertions; add `assert.equal(e[0].label, "EMBEDDED")` and `assert.equal(e[0].edge_kind, "embedded")` to the first (`weight ~1`) test.
- UPDATE `docPairContributions` tests (lines 278-303): replace `assert.equal(out[0].type, "person-business")` / `"person-person"` with `assert.equal(out[0].label, "EMBEDDED")` and `assert.equal(out[0].edge_kind, "embedded")`.
- UPDATE the `graphDdl v2` test (lines 313-320): change the edge PK assertion and add columns:

```javascript
test("graphDdl v2 adds block_key, edge accumulators, edge_kind, and primary keys", () => {
  const d = core.graphDdl(OPTS);
  assert.match(d.nodes, /block_key\s+CHAR\(64\)/);
  assert.match(d.nodes, /PRIMARY KEY \(node\)/);
  assert.match(d.edges, /edge_label\s+CHAR\(32\) NOT NULL/);
  assert.match(d.edges, /edge_kind\s+CHAR\(16\) NOT NULL/);
  assert.match(d.edges, /sum_wv\s+DOUBLE/);
  assert.match(d.edges, /PRIMARY KEY \(node1, node2, edge_label\)/);
});
```

ADD a new test:

```javascript
test("computeEdges emits EMBEDDED layer labels", () => {
  const ents = [{name:"A",label:"People",docIds:[1]},{name:"B",label:"People",docIds:[2]}];
  const e = core.computeEdges(ents, new Map([[1,[1,0]],[2,[1,0]]]));
  assert.equal(e[0].label, "EMBEDDED");
  assert.equal(e[0].edge_kind, "embedded");
  assert.equal(e[0].type, undefined);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — edges still have `type`; DDL lacks `edge_label`/`edge_kind`.

- [ ] **Step 3: Retire edgeType; relabel edges; extend the DDL**

In `index.html`, DELETE `edgeType` (lines 907-912).

In `docPairContributions`, REPLACE the `add` closure's edge-object creation (line 934) so it no longer calls `edgeType` and sets the EMBEDDED label:

```javascript
    if (!cur){ cur = {node1:n1, node2:n2, label:"EMBEDDED", edge_kind:"embedded", d_wv:0, d_w:0}; acc.set(key,cur); }
```

(The `l1`/`l2` locals at lines 930-931 become unused; delete lines 931 and the `la`/`lb` params are still needed for the flip check — keep the `add` signature `(na, la, nb, lb, del)` but you may drop the `l1`/`l2` computation on line 931. Leave line 930's `n1`/`n2` flip logic intact.)

In `computeEdges`, REPLACE the `edges.push(...)` line (line 972) with:

```javascript
      edges.push({ node1: n1, node2: n2, label: "EMBEDDED", edge_kind: "embedded", weight, sum_wv: sumWV, sum_w: sumW });
```

In `graphDdl`, REPLACE the `edges` table definition (lines 1004-1012) with:

```javascript
  const edges = head("edges")+"\n(\n"+
    "    node1  CHAR(64) NOT NULL,\n"+
    "    node2  CHAR(64) NOT NULL,\n"+
    "    label      VARCHAR[] NOT NULL,\n"+
    "    edge_label CHAR(32) NOT NULL,\n"+
    "    edge_kind  CHAR(16) NOT NULL,\n"+
    "    weight FLOAT NOT NULL,\n"+
    "    sum_wv DOUBLE,\n"+
    "    sum_w  DOUBLE,\n"+
    "    created_at TIMESTAMP NOT NULL,\n"+
    "    PRIMARY KEY (node1, node2, edge_label)\n)";
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS for Task 5 tests (emitter suites — `edgeInserts`/`edgeUpserts` — still fail; fixed in Task 6).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat(core): two-layer edge shape (label/edge_kind) + edge_label PK; retire edgeType"
```

---

## Task 6: CORE — edge emitters with edge_label + edge_kind

**Files:**
- Modify: `index.html` (CORE block 5: `edgeInserts` 1038-1051, `edgeUpserts` 1052-1064, `edgeAccumQuery` 1091-1094)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Consumes: edge objects `{node1, node2, label, edge_kind, weight, sum_wv, sum_w}` (Task 5), `arrayLit`, `guardName`, `num`, `esc`, `inList`.
- Produces (CORE): `edgeInserts(edges, opts, threshold)` and `edgeUpserts(edges, opts)` emit columns `(node1, node2, label, edge_label, edge_kind, weight, sum_wv, sum_w, created_at)`. `edgeAccumQuery(table, names)` selects `node1, node2, edge_label, sum_wv, sum_w`.

- [ ] **Step 1: Write the failing tests**

In `scripts/test_graph.mjs`:
- UPDATE the `nodeInserts and edgeInserts` test (lines 168-182): the `edges` fixtures need the new shape; replace its edge fixtures and assertions:

```javascript
  const edges = [{node1:"A",node2:"B",label:"EMBEDDED",edge_kind:"embedded",weight:0.73,sum_wv:7.3,sum_w:10},
                 {node1:"A",node2:"C",label:"EMBEDDED",edge_kind:"embedded",weight:0.2,sum_wv:2,sum_w:10}];
  const ei = core.edgeInserts(edges, OPTS, 0.5);
  assert.equal(ei.length, 1);
  assert.match(ei[0], /ARRAY\['EMBEDDED'\]/);
  assert.match(ei[0], /'EMBEDDED', 'embedded'/);   // edge_label, edge_kind scalars
  assert.match(ei[0], /0\.73/);
  assert.ok(!/'C'/.test(ei[0]));                   // below-threshold dropped
```

- UPDATE the `edgeUpserts` test (lines 340-350):

```javascript
test("edgeUpserts stores all edges with accumulators, edge_kind, and the upsert hint", () => {
  const edges = [
    {node1:"A",node2:"B",label:"EMBEDDED",edge_kind:"embedded",weight:0.7,sum_wv:7,sum_w:10},
    {node1:"Kaan",node2:"Acme",label:"WORKS_AT",edge_kind:"relation",weight:1.0,sum_wv:1,sum_w:1},
  ];
  const s = core.edgeUpserts(edges, OPTS);
  assert.match(s[0], /INSERT INTO \/\* KI_HINT_UPDATE_ON_EXISTING_PK \*\/ graph_edges_20260101/);
  assert.match(s[0], /'A', 'B', ARRAY\['EMBEDDED'\], 'EMBEDDED', 'embedded'/);
  assert.match(s[0], /'Kaan', 'Acme', ARRAY\['WORKS_AT'\], 'WORKS_AT', 'relation'/);
});
```

- UPDATE the `edgeAccumQuery` assertion inside the `read-back queries` test (lines 374-375):

```javascript
  assert.equal(core.edgeAccumQuery("e", ["A","B"]),
    "SELECT node1, node2, edge_label, sum_wv, sum_w FROM e WHERE node1 IN ('A','B') OR node2 IN ('A','B')");
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — emitters still emit the old column set.

- [ ] **Step 3: Update the emitters**

In `index.html`, REPLACE `edgeInserts` (lines 1038-1051) with:

```javascript
function edgeInserts(edges, opts, threshold){
  const t = graphTableName(opts.prefix,"edges",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const cols = "(node1, node2, label, edge_label, edge_kind, weight, sum_wv, sum_w, created_at)";
  const kept = edges.filter(e => e.weight >= threshold);
  const out = [];
  for (let i=0;i<kept.length;i+=size){
    const rows = kept.slice(i,i+size).map(e => {
      const lbl = e.label || "EMBEDDED", kind = e.edge_kind || "embedded";
      return "    ('"+esc(guardName(e.node1))+"', '"+esc(guardName(e.node2))+"', "+arrayLit([lbl],"str")+", '"+
        esc(lbl.slice(0,32))+"', '"+esc(kind)+"', "+num(e.weight)+", "+
        num(e.sum_wv!=null?e.sum_wv:e.weight)+", "+num(e.sum_w!=null?e.sum_w:1)+", '"+opts.createdAt+"')";
    });
    out.push("INSERT INTO "+t+"\n"+cols+"\nVALUES\n"+rows.join(",\n"));
  }
  return out;
}
```

REPLACE `edgeUpserts` (lines 1052-1064) with:

```javascript
function edgeUpserts(edges, opts){
  const t = graphTableName(opts.prefix,"edges",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const cols = "(node1, node2, label, edge_label, edge_kind, weight, sum_wv, sum_w, created_at)";
  const out = [];
  for (let i=0;i<edges.length;i+=size){
    const rows = edges.slice(i,i+size).map(e => {
      const lbl = e.label || "EMBEDDED", kind = e.edge_kind || "embedded";
      return "    ('"+esc(guardName(e.node1))+"', '"+esc(guardName(e.node2))+"', "+arrayLit([lbl],"str")+", '"+
        esc(lbl.slice(0,32))+"', '"+esc(kind)+"', "+num(e.weight)+", "+num(e.sum_wv)+", "+num(e.sum_w)+", '"+opts.createdAt+"')";
    });
    out.push("INSERT INTO /* KI_HINT_UPDATE_ON_EXISTING_PK */ "+t+"\n"+cols+"\nVALUES\n"+rows.join(",\n"));
  }
  return out;
}
```

REPLACE `edgeAccumQuery` (lines 1091-1094) with:

```javascript
function edgeAccumQuery(table, names){
  const l = inList(names,"str");
  return "SELECT node1, node2, edge_label, sum_wv, sum_w FROM "+table+" WHERE node1 IN "+l+" OR node2 IN "+l;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (whole file green now).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat(core): edge emitters carry edge_label + edge_kind; edgeAccumQuery keys on edge_label"
```

---

## Task 7: CORE — extraction folding, schema/prompt, and relation edges

**Files:**
- Modify: `index.html` (add to a CORE block — place near `mergeMentions`/`resolveIncremental`, CORE block 3, so `normalizeName`/`sameEntity` are in scope)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Consumes: `normLabel`, `normPredicate` (Task 3), `normalizeName`, `sameEntity` (Task 4).
- Produces (CORE): `EXTRACT_SCHEMA` (object); `extractionPrompt()` -> string; `foldExtraction(obj, docs)` -> `{mentions:[{surface,label,docId}], relations:[{subject,predicate,object,docIds}]}`; `buildRelationEdges(relations, entities)` -> `{edges:[{node1,node2,label,edge_kind:"relation",weight:1,sum_wv:1,sum_w:1,docIds}], dropped:int}`.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_graph.mjs`:

```javascript
test("foldExtraction folds labels/predicates and recovers doc_ids", () => {
  const docs = [{id:1,text:"Kaan works at BabelStreet in Arlington."},{id:2,text:"BabelStreet is a company."}];
  const obj = {
    entities: [
      {name:"Kaan", label:"person", doc_ids:[1]},
      {name:"BabelStreet", label:"company", doc_ids:[]},        // recover by scan -> 1,2
      {name:"", label:"People", doc_ids:[1]},                    // dropped (empty)
    ],
    relations: [
      {subject:"Kaan", predicate:"works at", object:"BabelStreet", doc_ids:[1]},
      {subject:"Kaan", predicate:"WORKS_AT", object:"", doc_ids:[1]},  // dropped (empty object)
    ],
  };
  const r = core.foldExtraction(obj, docs);
  assert.deepEqual(r.mentions.filter(m=>m.surface==="Kaan"), [{surface:"Kaan",label:"People",docId:1}]);
  const bs = r.mentions.filter(m=>m.surface==="BabelStreet").map(m=>m.docId).sort();
  assert.deepEqual(bs, [1,2]);
  assert.equal(r.relations.length, 1);
  assert.equal(r.relations[0].predicate, "WORKS_AT");
});

test("buildRelationEdges resolves endpoints, drops unresolved, no self-loops", () => {
  const entities = [
    {name:"Kaan Karamete", label:"People", aliases:["Kaan","Kaan Karamete"]},
    {name:"BabelStreet", label:"Business", aliases:["BabelStreet"]},
  ];
  const relations = [
    {subject:"Kaan", predicate:"WORKS_AT", object:"BabelStreet", docIds:[1]},
    {subject:"Kaan", predicate:"LEADS", object:"Nowhere Corp", docIds:[1]},   // object unresolved -> dropped
    {subject:"Kaan", predicate:"RELATED_TO", object:"Kaan Karamete", docIds:[1]}, // self -> dropped
  ];
  const r = core.buildRelationEdges(relations, entities);
  assert.equal(r.edges.length, 1);
  assert.equal(r.dropped, 2);
  const e = r.edges[0];
  assert.equal(e.node1, "Kaan Karamete");   // subject -> canonical
  assert.equal(e.node2, "BabelStreet");     // object  -> canonical (direction preserved)
  assert.equal(e.label, "WORKS_AT");
  assert.equal(e.edge_kind, "relation");
  assert.equal(e.weight, 1);
  assert.equal(e.sum_wv, 1); assert.equal(e.sum_w, 1);
});

test("buildRelationEdges keeps one row per (pair, predicate)", () => {
  const entities = [{name:"A",label:"Business",aliases:["A"]},{name:"B",label:"Business",aliases:["B"]}];
  const rels = [
    {subject:"A",predicate:"OWNS",object:"B",docIds:[1]},
    {subject:"A",predicate:"OWNS",object:"B",docIds:[2]},   // dup pair+predicate -> collapsed
    {subject:"A",predicate:"AFFILIATED_WITH",object:"B",docIds:[3]},
  ];
  const r = core.buildRelationEdges(rels, entities);
  assert.equal(r.edges.length, 2);
});

test("EXTRACT_SCHEMA enumerates the five types and the predicate set", () => {
  const ent = core.EXTRACT_SCHEMA.properties.entities.items.properties.label.enum;
  assert.deepEqual(ent, ["People","Business","Organization","Facility","Location"]);
  const pred = core.EXTRACT_SCHEMA.properties.relations.items.properties.predicate.enum;
  assert.ok(pred.includes("WORKS_AT") && pred.includes("RELATED_TO"));
  assert.ok(typeof core.extractionPrompt() === "string" && core.extractionPrompt().length > 50);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `foldExtraction`/`buildRelationEdges`/`EXTRACT_SCHEMA`/`extractionPrompt` undefined.

- [ ] **Step 3: Add the functions to CORE block 3**

In `index.html`, inside CORE block 3 (after `resolveIncremental`, before the `/* CORE:END */` at line 899), add:

```javascript
const EXTRACT_SCHEMA = {
  type:"object",
  properties:{
    entities:{ type:"array", items:{ type:"object", properties:{
      name:{type:"string"},
      label:{type:"string", enum:["People","Business","Organization","Facility","Location"]},
      doc_ids:{type:"array", items:{type:"integer"}}
    }, required:["name","label","doc_ids"] } },
    relations:{ type:"array", items:{ type:"object", properties:{
      subject:{type:"string"},
      predicate:{type:"string", enum:["WORKS_AT","FOUNDED","LEADS","MEMBER_OF","LOCATED_IN","HEADQUARTERED_IN","PART_OF","OWNS","AFFILIATED_WITH","VISITED","RELATED_TO"]},
      object:{type:"string"},
      doc_ids:{type:"array", items:{type:"integer"}}
    }, required:["subject","predicate","object","doc_ids"] } }
  },
  required:["entities","relations"]
};
function extractionPrompt(){
  return "You are an entity and relation extractor. Read every document (each prefixed with its [n] id). "+
    "Extract EVERY distinct named entity and label each as exactly one of: "+
    "People (a human), Business (a for-profit company), Organization (government, agency, NGO, academic, or association), "+
    "Facility (a built structure or venue: airport, stadium, hospital, museum, plant), or Location (a geographic place). "+
    "Then extract relations between the entities using ONLY these predicates: "+
    "WORKS_AT, FOUNDED, LEADS, MEMBER_OF, LOCATED_IN, HEADQUARTERED_IN, PART_OF, OWNS, AFFILIATED_WITH, VISITED, or RELATED_TO (fallback). "+
    "For each entity and relation, list every doc id [n] it appears in. "+
    "Return ONLY JSON of the form: "+
    "{\"entities\":[{\"name\":\"...\",\"label\":\"People|Business|Organization|Facility|Location\",\"doc_ids\":[int]}],"+
    "\"relations\":[{\"subject\":\"...\",\"predicate\":\"WORKS_AT|...\",\"object\":\"...\",\"doc_ids\":[int]}]}.";
}
function foldExtraction(obj, docs){
  const valid = new Set(docs.map(d => d.id));
  const recover = (surface, ids) => {
    let out = (Array.isArray(ids) ? ids : []).filter(n => valid.has(n));
    if (!out.length){
      const needle = String(surface).toLowerCase();
      out = docs.filter(d => d.text.toLowerCase().includes(needle)).map(d => d.id);
    }
    return out;
  };
  const mentions = [];
  for (const e of (obj && obj.entities || [])){
    const surface = String(e.name || "").trim();
    if (!surface) continue;
    const label = normLabel(e.label);
    for (const id of recover(surface, e.doc_ids)) mentions.push({surface, label, docId:id});
  }
  const relations = [];
  for (const r of (obj && obj.relations || [])){
    const subject = String(r.subject || "").trim();
    const object  = String(r.object  || "").trim();
    if (!subject || !object) continue;
    relations.push({subject, predicate:normPredicate(r.predicate), object, docIds:recover(subject, r.doc_ids)});
  }
  return {mentions, relations};
}
function buildRelationEdges(relations, entities){
  const index = [];
  for (const e of (entities||[])){
    const forms = [e.name, ...((e.aliases)||[])];
    for (const f of forms) index.push({norm:normalizeName(f), name:e.name, label:e.label});
  }
  const resolve = (surface) => {
    const key = normalizeName(surface);
    const hit = index.find(x => x.norm === key);
    if (hit) return hit;
    for (const e of (entities||[])) if (sameEntity(e.label, e.name, surface)) return {name:e.name, label:e.label};
    return null;
  };
  const acc = new Map(); let dropped = 0;
  for (const r of (relations||[])){
    const s = resolve(r.subject), o = resolve(r.object);
    if (!s || !o){ dropped++; continue; }
    if (s.name === o.name){ dropped++; continue; }
    const predicate = normPredicate(r.predicate);
    const key = s.name+" "+o.name+" "+predicate;
    if (acc.has(key)) continue;
    acc.set(key, {node1:s.name, node2:o.name, label:predicate, edge_kind:"relation",
      weight:1.0, sum_wv:1.0, sum_w:1.0, docIds:(r.docIds||[]).slice()});
  }
  return {edges:[...acc.values()], dropped};
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat(core): extraction folding, combined schema/prompt, and relation-edge builder"
```

---

## Task 8: DOM — extraction UI + `extractLLM` transport rewrite

**Files:**
- Modify: `index.html` (extraction panel HTML lines ~213-244; `extractLLM` lines 1232-1284; `normLabel` old copy lines 1285-1293 removed; provider-change wiring lines 1510-1517)

**Interfaces:**
- Consumes: `EXTRACT_SCHEMA`, `extractionPrompt`, `foldExtraction` (Task 7).
- Produces: `extractLLM(docs)` returns `{mentions, relations}` by POSTing to `/claude` or `/gemini`. New element ids `claudeOpts`/`claudeModel`, `geminiOpts`/`geminiModel`. Provider dropdown values `local`/`claude`/`gemini`.

- [ ] **Step 1: Replace the extraction provider HTML**

REPLACE the `<select id="extractProvider">` options (lines 214-218) with:

```html
          <select id="extractProvider">
            <option value="local">Local heuristic (offline)</option>
            <option value="claude">Claude (Anthropic)</option>
            <option value="gemini">Gemini (Google)</option>
          </select>
```

REPLACE the `#llmOpts` and `#ollamaChatOpts` blocks (lines 228-239) with:

```html
      <div id="claudeOpts" style="display:none">
        <div class="field">
          <label for="claudeModel">Claude model</label>
          <select id="claudeModel">
            <option value="claude-haiku-4-5-20251001">claude-haiku-4-5 (fast)</option>
            <option value="claude-opus-4-8">claude-opus-4-8 (best)</option>
          </select>
        </div>
        <p class="hint">Runs through the <code>/claude</code> route using the CLI stored login. No API key in the browser.</p>
      </div>
      <div id="geminiOpts" style="display:none">
        <div class="field">
          <label for="geminiModel">Gemini model</label>
          <select id="geminiModel">
            <option value="gemini-2.5-flash">gemini-2.5-flash (fast)</option>
            <option value="gemini-2.5-pro">gemini-2.5-pro (best)</option>
          </select>
        </div>
        <p class="hint">Runs through the <code>/gemini</code> route (Vertex). Run <code>gcloud auth login</code> once.</p>
      </div>
```

- [ ] **Step 2: Rewrite `extractLLM` and remove the old `normLabel`**

REPLACE `extractLLM` (lines 1232-1284) AND the old `normLabel` (lines 1285-1293) with a single new `extractLLM` (the five-type `normLabel` now lives in CORE from Task 3, so delete this DOM copy entirely):

```javascript
async function extractLLM(docs){
  const provider = $("extractProvider").value;                 // "claude" | "gemini"
  const model = provider === "claude" ? $("claudeModel").value : $("geminiModel").value;
  const route = provider === "claude" ? "/claude" : "/gemini";
  const prompt = extractionPrompt() + "\n\nDOCUMENTS:\n" + docs.map(d => "["+d.id+"] "+d.text).join("\n\n");
  const res = await fetch(route, {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({prompt, schema:EXTRACT_SCHEMA, model})});
  const text = await res.text();
  let env; try { env = JSON.parse(text); } catch(e){ throw new Error(route+" sent non-JSON: "+text.slice(0,200)); }
  if (env.status === "ERROR") throw new Error(env.message || (route+" error"));
  return foldExtraction(env.data || {}, docs);                 // {mentions, relations}
}
```

- [ ] **Step 3: Update the provider-change wiring**

REPLACE the `extractProvider` change listener (lines 1510-1514) with:

```javascript
$("extractProvider").addEventListener("change", () => {
  const v = $("extractProvider").value;
  $("claudeOpts").style.display = v === "claude" ? "block" : "none";
  $("geminiOpts").style.display = v === "gemini" ? "block" : "none";
});
```

- [ ] **Step 4: Manual smoke test (no automated harness for DOM)**

Run: `python3 scripts/serve.py --port 8181` and open http://localhost:8181. Paste `samples/*.txt`, Generate embeddings, choose Extraction → **Claude (Anthropic)**, Extract entities. Expected: entities render without a console error and the log reports a count. (Full five-type/relation rendering is verified in Task 9.) If `claude` is not logged in this is expected to error with an actionable message — that still exercises the path.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(app): Claude + Gemini extraction providers; extractLLM returns {mentions, relations}"
```

---

## Task 9: DOM — integration (entities coloring, relation edges, two-layer store)

**Files:**
- Modify: `index.html` (module vars line ~457; `btnExtract` handler 1518-1532; `resolveApi` 1295-1306; `renderEntities` 1187-1205; `btnBuildGraph` 1535-1545; `appendBatch` 1620-1672; `renderGraph` — read current source)

**Interfaces:**
- Consumes: `buildRelationEdges` (Task 7), `TYPES` (Task 3), five-type edges (Tasks 5-6), `extractLLM` (Task 8).
- Produces: module var `RELATIONS`; entities colored by `TYPES[label].colorVar`; `EDGES` holds embedded + relation edges; store paths emit both layers.

- [ ] **Step 1: Add the RELATIONS module var**

After line 458 (`let EDGES = [];`), add:

```javascript
let RELATIONS = [];      // {subject, predicate, object, docIds} from the last LLM extraction
```

- [ ] **Step 2: Update the extract button handler**

REPLACE the body of the `btnExtract` click handler (lines 1522-1530) with:

```javascript
    const docs = DOCS.map(d => ({id:d.id, text:d.text}));
    const ex = $("extractProvider").value === "local"
      ? {mentions: extractLocalMentions(docs), relations: []}
      : await extractLLM(docs);
    const mode = $("resolveMode").value;
    ENTITIES = mode === "api" ? await resolveApi(ex.mentions) : mergeMentions(ex.mentions, mode);
    RELATIONS = ex.relations || [];
    for (const e of ENTITIES){ if (e.name.length > 64) log("Name over 64 chars will be truncated for CHAR(64): "+e.name, "warn"); }
    renderEntities();
    const byType = {}; for (const e of ENTITIES) byType[e.label] = (byType[e.label]||0)+1;
    const summary = Object.keys(TYPES).filter(t=>byType[t]).map(t=>byType[t]+" "+t).join(", ") || "0";
    log("Extracted "+ENTITIES.length+" entities ("+summary+"); "+RELATIONS.length+" relations.", "ok");
    if ($("extractProvider").value === "local" && ENTITIES.length) log("Local extraction produces no relations — only the EMBEDDED similarity layer will be built.", "warn");
```

- [ ] **Step 3: Fix `resolveApi` label handling**

In `resolveApi` (line 1302), REPLACE `label: e.label === "Business" ? "Business":"Person",` with:

```javascript
      name:String(e.name), label: normLabel(e.label),
```

- [ ] **Step 4: Color entities by type**

In `renderEntities`, REPLACE line 1193 (`const color = e.label === "Person" ? "var(--signal)" : "var(--warm)";`) with:

```javascript
    const color = "var("+((TYPES[e.label] && TYPES[e.label].colorVar) || "--muted")+")";
```

- [ ] **Step 5: Build graph merges both layers**

In the `btnBuildGraph` handler, REPLACE line 1541 (`EDGES = computeEdges(ENTITIES, dv);`) with:

```javascript
    const embedded = computeEdges(ENTITIES, dv);
    const rel = buildRelationEdges(RELATIONS, ENTITIES);
    if (rel.dropped) log(rel.dropped+" relation(s) dropped (endpoint not in entity set).", "warn");
    EDGES = embedded.concat(rel.edges);
    EDGES.sort((a,b) => b.weight - a.weight);
```

- [ ] **Step 6: Update `appendBatch` for the two-layer accumulator keying and relation upserts**

In `appendBatch`:

(a) After the extraction call, capture relations. REPLACE line 1622 with:

```javascript
    const ex = $("extractProvider").value === "local"
      ? {mentions: extractLocalMentions(docs), relations: []}
      : await extractLLM(docs);
    const mentions = ex.mentions;
    RELATIONS = ex.relations || [];
```

(b) The accumulator lookup must key on `edge_label`. REPLACE lines 1663-1671 (from `const names = ...` through the `EDGES.sort(...)`) with:

```javascript
    const relBuilt = buildRelationEdges(RELATIONS, ENTITIES);
    if (relBuilt.dropped) log(relBuilt.dropped+" relation(s) dropped (endpoint not in entity set).", "warn");
    const layerDeltas = deltas.concat(relBuilt.edges.map(e => ({node1:e.node1, node2:e.node2, label:e.label,
      edge_kind:e.edge_kind, d_wv:e.sum_wv, d_w:e.sum_w})));
    const names = [...new Set(layerDeltas.flatMap(e => [e.node1, e.node2]))];
    const accum = new Map();
    if (names.length){
      const ea = await readRows(edgeAccumQuery(graphTableName(opts.prefix,"edges",opts.stamp,opts.schema), names));
      if (ea) for (const [n1,n2,el,swv,sw] of ea.rows) accum.set(n1+" "+n2+" "+el, {sum_wv:swv||0, sum_w:sw||0});
    }
    EDGES = layerDeltas.map(e => { const m = mergeEdgeAccum(accum.get(e.node1+" "+e.node2+" "+e.label), {d_wv:e.d_wv, d_w:e.d_w});
      return {node1:e.node1, node2:e.node2, label:e.label, edge_kind:e.edge_kind, weight:m.weight, sum_wv:m.sum_wv, sum_w:m.sum_w}; });
    EDGES.sort((a,b) => b.weight - a.weight);
```

- [ ] **Step 7: Update `renderGraph` for the new edge shape**

Read the current `renderGraph` (search `function renderGraph` in `index.html`). It references `edge.type` (the retired field). REPLACE each `e.type`/`edge.type` reference with `e.label` (the predicate or `"EMBEDDED"`), and where it distinguishes styling, branch on `e.edge_kind === "relation"` vs `"embedded"`. Keep the existing layout/threshold logic. (Concretely: the label text shown per edge becomes `e.label`; relation edges may be drawn with a distinct accent — reuse an existing type color var, e.g. relation → `var(--org)`, embedded → `var(--muted)`.)

- [ ] **Step 8: Manual smoke test**

Run: `python3 scripts/serve.py --port 8181`. With `claude` logged in: paste a mixed sample (people + companies + a place), Generate embeddings, Extraction → Claude, Extract entities → confirm distinctly colored types render and the log shows a per-type summary + relation count. Build graph → confirm EDGES includes relation edges. Copy graph SQL → confirm the edge INSERTs carry `edge_label`/`edge_kind` and both `ARRAY['EMBEDDED']` and `ARRAY['<PREDICATE>']` rows appear, plus a runnable `CREATE UNDIRECTED GRAPH`.

- [ ] **Step 9: Run the full CORE + serve suites (regression)**

Run: `node --test scripts/test_graph.mjs && python3 scripts/test_serve.py`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add index.html
git commit -m "feat(app): two-layer graph integration — type coloring, relation edges, incremental upserts"
```

---

## Task 10: Docs — schema.sql, SETUP.md, CLAUDE.md

**Files:**
- Modify: `sql/schema.sql`, `SETUP.md`, `CLAUDE.md`

**Interfaces:** none (documentation). Must match the emitters from Tasks 5-6 exactly.

- [ ] **Step 1: Update `sql/schema.sql`**

Read `sql/schema.sql`. Update the `graph_edges_<datestamp>` DDL to match `graphDdl().edges` from Task 5: add `edge_label CHAR(32) NOT NULL` and `edge_kind CHAR(16) NOT NULL`, change the PK to `PRIMARY KEY (node1, node2, edge_label)`, and update the `label` column comment to note `ARRAY['EMBEDDED']` (similarity) vs `ARRAY['<PREDICATE>']` (relation). Keep the node and membership tables as-is (they are unchanged).

- [ ] **Step 2: Update `SETUP.md`**

Replace the Ollama *extraction* verification bullet in Section 5 with Claude/Gemini provider setup:
- Add a short "LLM providers for extraction" subsection: Claude needs a logged-in `claude` CLI (stored login); Gemini needs `gcloud auth login` and a project (shown by `serve.py` on start). Launch line: `python3 scripts/serve.py --port 8181 --gcp-project <proj> --gcp-region global`.
- Keep the Ollama *embeddings* verification (model discovery, embedding round-trip) — only remove the Ollama *extraction* bullet.
- Update the extraction round-trip bullet to: Extraction → **Claude (Anthropic)** (or **Gemini (Google)**), Extract entities → five distinctly colored types render (People indigo, Business amber, Organization teal, Facility plum, Location green) and relations appear.

- [ ] **Step 3: Update `CLAUDE.md`**

- In "How the app is wired" §3 (Extract entities): change the two-type (Person/Business) description to the five-type set and note the combined entities+relations LLM call.
- Replace the "Ollama transport option for extraction" paragraph with the Claude/Gemini providers: `/claude` (CLI subprocess, stored login, models claude-haiku-4-5-20251001 / claude-opus-4-8) and `/gemini` (Vertex REST via gcloud token, models gemini-2.5-flash / gemini-2.5-pro). State that Ollama *embeddings* remain and Ollama *chat extraction* is retired.
- Update the "Graph edges and tables" section: the edge table now has `edge_label CHAR(32)`, `edge_kind CHAR(16)`, PK `(node1, node2, edge_label)`; edges are a two-layer multigraph — `ARRAY['EMBEDDED']` similarity edges (`edge_kind='embedded'`) and `ARRAY['<PREDICATE>']` relation edges (`edge_kind='relation'`, weight 1.0). Note the closed predicate vocabulary.
- Update the palette section: five colors (People `--signal`, Business `--warm`, Organization `--org`, Facility `--facility`, Location `--loc`).
- Update the "Testing the pure core functions" list to include `foldExtraction`, `buildRelationEdges`, `normLabel`, `normPredicate`, `classifySpan` (five-type), and note `scripts/test_serve.py` now covers `run_claude`/`run_gemini`.

- [ ] **Step 4: Verify no stale references**

Run: `grep -niE "person-business|person-person|business-business" sql/schema.sql CLAUDE.md` → expected: no matches (or only historical notes explicitly marked retired).

- [ ] **Step 5: Commit**

```bash
git add sql/schema.sql SETUP.md CLAUDE.md
git commit -m "docs: five-type ontology, two-layer edges, Claude/Gemini providers"
```

---

## Self-Review Notes (planner)

- **Spec coverage:** five types (Task 3) ✓; TYPES source of truth (Task 3) ✓; palette (Task 3) ✓; People token (Tasks 3-4, 8-9) ✓; combined LLM call + guards (Tasks 7-8) ✓; local best-effort classifier (Task 3) ✓; predicate vocabulary (Tasks 3, 7) ✓; per-type disambiguation (Task 4) ✓; two-layer edges + edge_kind + edge_label PK (Tasks 5-6) ✓; buildRelationEdges (Task 7) ✓; createGraphSql over both layers (unchanged — verified it selects `label` + `weight`) ✓; Claude + Gemini transport (Tasks 1-2, 8) ✓; Ollama extraction retired, embeddings kept (Tasks 8, 10) ✓; testing (every CORE/serve task) ✓; docs (Task 10) ✓.
- **Ruling on edge PK** (scalar `edge_label`) is applied consistently across `graphDdl`, `edgeInserts`, `edgeUpserts`, `edgeAccumQuery`, and the `appendBatch` accumulator key.
- **createGraphSql** is intentionally left unchanged: it already selects `node1, node2, label, (1 - weight) AS WEIGHT_VALUESPECIFIED`, which now spans both layers. No task modifies it.
- **Type consistency:** edge objects use `{label, edge_kind}` everywhere after Task 5; `type` is fully retired (Task 5 deletes `edgeType` and its test). `foldExtraction` returns `{mentions, relations}`; both orchestrators (Tasks 8-9) read those fields.
